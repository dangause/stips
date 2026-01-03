#!/usr/bin/env bash
#
# run_drp_recal.sh — Complete DRP pipeline with Stage 2 recalibration
#
# Usage:
#   ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
#     --nights-file nights.txt \
#     --tract 1825 \
#     --jobs 4
#
# This script runs the full DRP pipeline with recalibration:
#   1. Bootstrap repo (if needed)
#   2. Download raw data (optional)
#   3. Process calibs (10_calibs_recal.sh)
#   4. Process science Stage 1 (20_science_recal.sh)
#   5. Run Stage 2 recalibration (21_recalibrate.sh)
#   6. Build coadds with recalibrated data (30_coadds_recal.sh)
#   7. Run difference imaging (40_diff_imaging_recal.sh) - optional
#

set -euo pipefail

# Force use of .env.recal by default
ENV_FILE="${ENV_FILE:-.env.recal}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Source logging utilities
source "$(dirname "$0")/../utilities/logging.sh"

########################################
# Defaults / CLI
########################################
NIGHTS_FILE=""
TRACT=""
RA=""
DEC=""
SKYMAP="${SKYMAP:-nickelRings-v1}"
OBJECT_FILTER=""
JOBS="${JOBS:-4}"
BANDS="${BANDS:-r}"

SKIP_DOWNLOAD=false
DOWNLOAD_OVERWRITE=false
SKIP_BOOTSTRAP=false
SKIP_CALIBS=false
SKIP_SCIENCE=false
SKIP_RECALIBRATE=false
SKIP_COADDS=false
SKIP_DIA=false

DRY_RUN=false
CONTINUE_ON_ERROR=false

# Exit codes
EXIT_CODE=0
FAILED_NIGHTS=()

usage() {
  cat <<USAGE
Usage: $0 --nights-file FILE --tract TRACT [options]

Required:
  --nights-file FILE       File with nights to process (YYYYMMDD per line)
  --tract TRACT            Tract number (or use --ra/--dec to auto-determine)

Tract Selection (alternative):
  --ra RA --dec DEC        RA/Dec in degrees (auto-determines tract)
  --skymap NAME            Skymap name for RA/Dec lookup (default: nickelRings-v1)

Optional:
  --object NAME            OBJECT filter for science processing
  --jobs N                 Parallel jobs for pipeline tasks (default: ${JOBS})
  --bands LIST             Comma-separated bands (default: r)

Download Options:
  --skip-download          Skip archive downloads
  --download-overwrite     Re-download even if files exist

Pipeline Control:
  --skip-bootstrap         Skip repository bootstrap
  --skip-calibs            Skip calibration processing
  --skip-science           Skip science Stage 1 processing
  --skip-recalibrate       Skip Stage 2 recalibration
  --skip-coadds            Skip coadd generation
  --skip-dia               Skip difference imaging
  --continue-on-error      Continue processing after failures
  --dry-run                Print commands without executing

Environment:
  ENV_FILE                 Environment file to source (default: .env.recal)

Examples:
  # Full pipeline with recalibration
  ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \\
    --nights-file nights.txt --tract 1825 --jobs 4

  # Skip already-done stages
  ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \\
    --nights-file nights.txt --tract 1825 \\
    --skip-bootstrap --skip-calibs --skip-science \\
    --jobs 4
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nights-file)         NIGHTS_FILE="${2:-}"; shift 2;;
    --tract)               TRACT="${2:-}"; shift 2;;
    --ra)                  RA="${2:-}"; shift 2;;
    --dec)                 DEC="${2:-}"; shift 2;;
    --skymap)              SKYMAP="${2:-}"; shift 2;;
    --object)              OBJECT_FILTER="${2:-}"; shift 2;;
    --jobs|-j)             JOBS="${2:-}"; shift 2;;
    --bands)               BANDS="${2:-}"; shift 2;;
    --skip-download)       SKIP_DOWNLOAD=true; shift;;
    --download-overwrite)  DOWNLOAD_OVERWRITE=true; shift;;
    --skip-bootstrap)      SKIP_BOOTSTRAP=true; shift;;
    --skip-calibs)         SKIP_CALIBS=true; shift;;
    --skip-science)        SKIP_SCIENCE=true; shift;;
    --skip-recalibrate)    SKIP_RECALIBRATE=true; shift;;
    --skip-coadds)         SKIP_COADDS=true; shift;;
    --skip-dia)            SKIP_DIA=true; shift;;
    --continue-on-error)   CONTINUE_ON_ERROR=true; shift;;
    --dry-run)             DRY_RUN=true; shift;;
    -h|--help)             usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

########################################
# Validation
########################################
[[ -n "$NIGHTS_FILE" ]] || { echo "ERROR: --nights-file required"; usage; }
[[ -f "$NIGHTS_FILE" ]] || { echo "ERROR: Nights file not found: $NIGHTS_FILE"; exit 2; }

if [[ -n "$TRACT" && ( -n "$RA" || -n "$DEC" ) ]]; then
  echo "ERROR: Cannot specify both --tract and --ra/--dec"; exit 2;
fi
if [[ -n "$RA" && -z "$DEC" ]] || [[ -z "$RA" && -n "$DEC" ]]; then
  echo "ERROR: Must specify both --ra and --dec together"; exit 2;
fi
if [[ -z "$TRACT" && -z "$RA" ]]; then
  echo "ERROR: Must specify either --tract or --ra/--dec"; exit 2;
fi
if [[ -n "$TRACT" ]] && ! [[ "$TRACT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --tract must be numeric"; exit 2;
fi
if [[ -z "${REPO:-}" ]]; then
  echo "ERROR: REPO is not set (check your ${ENV_FILE})"; exit 2;
fi

########################################
# Setup logging and RUN_ID
########################################
export RUN_ID="drp_recal_$(date -u +%Y%m%d_%H%M%S)_$$"
setup_logging "other" "" "" "" "run_drp_recal"
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "DRP with Recalibration Pipeline"
log_info "RUN_ID: $RUN_ID"
log_info "Environment: $ENV_FILE"
log_info "Repo: $REPO"
log_info "Nights file: $NIGHTS_FILE"
log_info "Tract: ${TRACT:-auto-determine from RA/Dec}"
log_info "Jobs: $JOBS"

########################################
# Helpers
########################################
run_or_dry() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    log_info "Running: $*"
    "$@"
  fi
}

read_nights() {
  local file="$1"
  local out=()
  while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | tr -d '[:space:]')"
    [[ -z "$line" ]] && continue
    out+=("$line")
  done < "$file"
  printf "%s\n" "${out[@]}"
}

NIGHTS=($(read_nights "$NIGHTS_FILE"))
log_info "Processing ${#NIGHTS[@]} nights: ${NIGHTS[*]}"

########################################
# Stage 0: Bootstrap
########################################
if [[ "$SKIP_BOOTSTRAP" == "false" ]]; then
  if [[ ! -f "$REPO/butler.yaml" ]]; then
    log_section "Bootstrap Repository"
    if ! run_or_dry ./scripts/pipeline/00_bootstrap_repo_recal.sh; then
      log_error "Bootstrap failed"
      exit 2
    fi
  else
    log_info "Repository exists, skipping bootstrap"
  fi
else
  log_info "Skipping bootstrap (--skip-bootstrap)"
fi

########################################
# Auto-determine tract from RA/Dec
########################################
if [[ -n "$RA" && -n "$DEC" ]] && [[ -z "$TRACT" ]]; then
  log_info "Auto-determining tract from RA=$RA, Dec=$DEC"
  RADEC_SCRIPT="./scripts/utilities/radec_to_tract.py"
  [[ -f "$RADEC_SCRIPT" ]] || { echo "ERROR: $RADEC_SCRIPT not found"; exit 2; }

  # Load LSST stack
  if [[ -n "${STACK_DIR:-}" && -f "${STACK_DIR}/loadLSST.bash" ]]; then
    source "${STACK_DIR}/loadLSST.bash" >/dev/null 2>&1
    setup lsst_distrib >/dev/null 2>&1
  fi

  CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.1.0}"
  PYTHON_CMD="/opt/anaconda3/envs/${CONDA_ENV}/bin/python"
  [[ -x "$PYTHON_CMD" ]] || PYTHON_CMD="python"

  TRACT=$($PYTHON_CMD "$RADEC_SCRIPT" "$RA" "$DEC" --skymap "$SKYMAP" --repo "$REPO" 2>&1)
  if [[ $? -ne 0 ]] || [[ -z "$TRACT" ]]; then
    echo "ERROR: Failed to determine tract: $TRACT"; exit 2;
  fi
  log_info "Determined tract: $TRACT"

  if ! [[ "$TRACT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Determined tract is not numeric: '$TRACT'"; exit 2;
  fi
fi

########################################
# Stage 0.5: Download
########################################
if [[ "$SKIP_DOWNLOAD" == "false" ]]; then
  log_section "Archive Downloads"
  for night in "${NIGHTS[@]}"; do
    DL_ARGS=(--night "$night")
    [[ "$DOWNLOAD_OVERWRITE" == "true" ]] && DL_ARGS+=(--overwrite)
    if ! run_or_dry ./scripts/pipeline/01_download_archive.sh "${DL_ARGS[@]}"; then
      log_warn "Download failed for night $night"
      FAILED_NIGHTS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
else
  log_info "Skipping downloads (--skip-download)"
fi

########################################
# Stage 1: Calibs
########################################
if [[ "$SKIP_CALIBS" == "false" ]]; then
  log_section "Calibrations"
  for night in "${NIGHTS[@]}"; do
    if ! run_or_dry ./scripts/pipeline/10_calibs_recal.sh --night "$night" --jobs "$JOBS"; then
      log_warn "Calibs failed for night $night"
      FAILED_NIGHTS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
else
  log_info "Skipping calibs (--skip-calibs)"
fi

########################################
# Stage 1: Science (single-visit)
########################################
if [[ "$SKIP_SCIENCE" == "false" ]]; then
  log_section "Science Stage 1 (Single-Visit)"
  for night in "${NIGHTS[@]}"; do
    SCI_ARGS=(--night "$night" --jobs "$JOBS")
    [[ -n "$OBJECT_FILTER" ]] && SCI_ARGS+=(--object "$OBJECT_FILTER")
    if ! run_or_dry ./scripts/pipeline/20_science_recal.sh "${SCI_ARGS[@]}"; then
      log_warn "Science Stage 1 failed for night $night"
      FAILED_NIGHTS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
else
  log_info "Skipping science Stage 1 (--skip-science)"
fi

########################################
# Stage 2: Recalibration
########################################
if [[ "$SKIP_RECALIBRATE" == "false" ]]; then
  log_section "Stage 2 Recalibration"
  RECAL_ARGS=(--nights-file "$NIGHTS_FILE" --tract "$TRACT" --jobs "$JOBS")
  [[ -n "$OBJECT_FILTER" ]] && RECAL_ARGS+=(--object "$OBJECT_FILTER")
  if ! run_or_dry ./scripts/pipeline/21_recalibrate.sh "${RECAL_ARGS[@]}"; then
    log_error "Recalibration failed"
    EXIT_CODE=1
    [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
  fi
else
  log_info "Skipping recalibration (--skip-recalibrate)"
fi

########################################
# Stage 3: Coadds (with recalibrated data)
########################################
if [[ "$SKIP_COADDS" == "false" ]]; then
  log_section "Coadds (Recalibrated)"
  IFS=',' read -r -a BAND_ARRAY <<< "$BANDS"
  for BAND in "${BAND_ARRAY[@]}"; do
    BAND="$(echo "$BAND" | tr -d '[:space:]')"
    [[ -z "$BAND" ]] && continue

    COADD_ARGS=(--nights-file "$NIGHTS_FILE" --band "$BAND" --tract "$TRACT" --jobs "$JOBS")
    if ! run_or_dry ./scripts/pipeline/30_coadds_recal.sh "${COADD_ARGS[@]}"; then
      log_warn "Coadds failed for band $BAND"
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
else
  log_info "Skipping coadds (--skip-coadds)"
fi

########################################
# Stage 4: Difference Imaging (optional)
########################################
if [[ "$SKIP_DIA" == "false" ]]; then
  log_section "Difference Imaging (Optional)"
  log_info "DIA step not yet implemented in recal pipeline"
  log_info "Use 40_diff_imaging_recal.sh manually if needed"
else
  log_info "Skipping DIA (--skip-dia)"
fi

########################################
# Summary
########################################
log_section "Pipeline Complete"
SUMMARY_TEXT="$(cat <<EOF
DRP with Recalibration Pipeline Summary
========================================

RUN_ID: $RUN_ID
Environment: $ENV_FILE
Repository: $REPO
Tract: $TRACT
Bands: $BANDS
Total nights: ${#NIGHTS[@]}

Results:
$(if [[ ${#FAILED_NIGHTS[@]} -gt 0 ]]; then echo "  Failed nights: ${FAILED_NIGHTS[*]}"; else echo "  All nights processed successfully"; fi)

Exit code: $EXIT_CODE
EOF
)"

write_summary "$SUMMARY_TEXT"

if [[ ${#FAILED_NIGHTS[@]} -gt 0 ]]; then
  log_warn "Some nights failed: ${FAILED_NIGHTS[*]}"
fi

print_log_summary

exit $EXIT_CODE
