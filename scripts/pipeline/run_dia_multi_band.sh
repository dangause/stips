#!/usr/bin/env bash
#
# run_dia_multi_band.sh — Calibs+science once, then DIA across multiple bands
# Usage example:
#   ./scripts/pipeline/run_dia_multi_band.sh \
#     --template-nights scripts/config/2020wnt/template_nights.txt \
#     --science-nights  scripts/config/2020wnt/sn_nights.txt \
#     --bands "b,v,r,i" \
#     --tract 1825 \
#     --object "2020wnt" \
#     --jobs 4
#
# Notes:
#   - Runs 10_calibs and 20_science once per night (no repetition per band)
#   - Builds a template per band (30_coadds) unless --skip-template-build or --auto-template is set
#   - Runs DIA (40_diff_imaging) per science night per band
#
# set -euo pipefail

########################################
# Defaults / CLI
########################################
TEMPLATE_NIGHTS_FILE=""
SCIENCE_NIGHTS_FILE=""
BANDS="r"
TRACT=""
OBJECT_FILTER=""
JOBS="${JOBS:-4}"
BAD_SUB_THRESH=""
SKIP_TEMPLATE_BUILD=false
AUTO_TEMPLATE=false
DRY_RUN=false
CONTINUE_ON_ERROR=false
SKIP_BOOTSTRAP=false
SKIP_CALIBS=false
SKIP_SCIENCE=false

# Exit codes: 0=success, 1=failures with --continue-on-error, 2=fatal error
EXIT_CODE=0
FAILED_CALIBS=()
FAILED_SCIENCE=()
FAILED_TEMPLATE=()
FAILED_DIA=()

usage() {
  cat <<USAGE
Usage: $0 --template-nights FILE --science-nights FILE --bands "r,i" --tract TRACT [options]

Required:
  --template-nights FILE   Nights file for template build (YYYYMMDD per line)
  --science-nights FILE    Nights file for science/DIA (YYYYMMDD per line)
  --bands LIST             Comma-separated bands (e.g., "r" or "b,v,r,i")
  --tract TRACT            Tract number (must be numeric)

Optional:
  --object NAME            OBJECT filter for science/DIA
  --jobs N                 Parallel jobs for pipeline tasks (default: ${JOBS})
  --bad-sub-threshold X    Override badSubtractionRatioThreshold for DIA

Template Options:
  --skip-template-build    Skip 30_coadds (use existing templates)
  --auto-template          Let 40_diff_imaging auto-discover templates (skips 30)

Pipeline Control:
  --skip-bootstrap         Skip repository bootstrap (fail if repo doesn't exist)
  --skip-calibs            Skip calibration processing (10_calibs.sh)
  --skip-science           Skip science processing (20_science.sh)
  --continue-on-error      Continue processing remaining nights/bands after failures
  --dry-run                Print commands without executing
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-nights) TEMPLATE_NIGHTS_FILE="${2:-}"; shift 2;;
    --science-nights)  SCIENCE_NIGHTS_FILE="${2:-}"; shift 2;;
    --bands)           BANDS="${2:-}"; shift 2;;
    --tract)           TRACT="${2:-}"; shift 2;;
    --object)          OBJECT_FILTER="${2:-}"; shift 2;;
    --jobs|-j)         JOBS="${2:-4}"; shift 2;;
    --bad-sub-threshold) BAD_SUB_THRESH="${2:-}"; shift 2;;
    --skip-template-build) SKIP_TEMPLATE_BUILD=true; shift 1;;
    --auto-template)   AUTO_TEMPLATE=true; shift 1;;
    --dry-run)         DRY_RUN=true; shift 1;;
    --continue-on-error) CONTINUE_ON_ERROR=true; shift 1;;
    --skip-bootstrap)  SKIP_BOOTSTRAP=true; shift 1;;
    --skip-calibs)     SKIP_CALIBS=true; shift 1;;
    --skip-science)    SKIP_SCIENCE=true; shift 1;;
  -h|--help)         usage;;
  *) echo "Unknown arg: $1"; usage;;
  esac
done

[[ -f ".env" ]] && { set -a; source .env; set +a; }

[[ -z "$TEMPLATE_NIGHTS_FILE" || -z "$SCIENCE_NIGHTS_FILE" || -z "$BANDS" || -z "$TRACT" ]] && usage
[[ ! -f "$TEMPLATE_NIGHTS_FILE" ]] && { echo "Template nights file not found: $TEMPLATE_NIGHTS_FILE"; exit 2; }
[[ ! -f "$SCIENCE_NIGHTS_FILE" ]] && { echo "Science nights file not found: $SCIENCE_NIGHTS_FILE"; exit 2; }
if ! [[ "$TRACT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --tract must be numeric (got '$TRACT')"; exit 2;
fi
if [[ -n "$BAD_SUB_THRESH" && ! "$BAD_SUB_THRESH" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "ERROR: --bad-sub-threshold must be numeric"; exit 2;
fi
if [[ -z "${REPO:-}" ]]; then
  echo "ERROR: REPO is not set (check your .env)"; exit 2;
fi

########################################
# Helpers
########################################
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
run_or_dry() { if [[ "$DRY_RUN" == "true" ]]; then echo "[DRY-RUN] $*"; else log "Running: $*"; "$@"; fi; }

# Track temp files for cleanup
TEMP_FILES=()
cleanup_temp_files() {
  for f in "${TEMP_FILES[@]}"; do
    [[ -f "$f" ]] && rm -f "$f"
  done
}
trap cleanup_temp_files EXIT

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

uniq_list() { tr ' ' '\n' | sed '/^\s*$/d' | sort -u; }

# Check if a template collection exists and has template_coadd datasets
template_exists() {
  local tract="$1"
  local band="$2"
  local template_dir="$REPO/templates/deep/tract${tract}/${band}"

  # Check if template directory exists and has subdirectories (indicating runs)
  if [[ ! -d "$template_dir" ]]; then
    return 1
  fi

  # Check if there are any run subdirectories with template data
  if find "$template_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | grep -q .; then
    # Directory exists and has subdirectories - assume it has data
    return 0
  fi

  return 1
}

########################################
# Stage 0: Bootstrap if needed
########################################
if [[ ! -f "$REPO/butler.yaml" ]]; then
  if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
    echo "ERROR: Repo not found ($REPO) and --skip-bootstrap set"; exit 2;
  fi
  log "Repo not found ($REPO); running bootstrap (00_bootstrap_repo.sh)"
  run_or_dry ./scripts/pipeline/00_bootstrap_repo.sh
fi

########################################
# Nights
########################################
TEMPLATE_NIGHTS=($(read_nights "$TEMPLATE_NIGHTS_FILE"))
SCIENCE_NIGHTS=($(read_nights "$SCIENCE_NIGHTS_FILE"))
ALL_NIGHTS=($(printf "%s\n" "${TEMPLATE_NIGHTS[@]}" "${SCIENCE_NIGHTS[@]}" | uniq_list))

########################################
# Stage 1: Calibs (once per night)
########################################
if [[ "$SKIP_CALIBS" == "true" ]]; then
  log "Skipping calibs (--skip-calibs)"
else
  for night in "${ALL_NIGHTS[@]}"; do
    if ! run_or_dry ./scripts/pipeline/10_calibs.sh --night "$night" --jobs "$JOBS"; then
      log "[WARN] Calibs failed for night $night"
      FAILED_CALIBS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
fi

########################################
# Stage 2: Science (once per night)
########################################
if [[ "$SKIP_SCIENCE" == "true" ]]; then
  log "Skipping science (--skip-science)"
else
  for night in "${ALL_NIGHTS[@]}"; do
    SCI_ARGS=(--night "$night" -j "$JOBS" --skip-coadds)
    [[ -n "$OBJECT_FILTER" ]] && SCI_ARGS+=(--object "$OBJECT_FILTER")
    if ! run_or_dry ./scripts/pipeline/20_science.sh "${SCI_ARGS[@]}"; then
      log "[WARN] Science failed for night $night"
      FAILED_SCIENCE+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
fi

########################################
# Stage 3/4: Per-band template + DIA
########################################
IFS=',' read -r -a BAND_ARRAY <<< "$BANDS"

for BAND in "${BAND_ARRAY[@]}"; do
  BAND="$(echo "$BAND" | tr -d '[:space:]')"
  [[ -z "$BAND" ]] && continue
  log "=== Band: $BAND ==="

  TEMPLATE_COLLECTION=""

  if [[ "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "false" ]]; then
    # Check if template already exists with data
    TEMPLATE_DIR="$REPO/templates/deep/tract${TRACT}/${BAND}"
    if [[ -d "$TEMPLATE_DIR" ]] && find "$TEMPLATE_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | grep -q .; then
      TEMPLATE_COLLECTION="templates/deep/tract${TRACT}/${BAND}"
      log "[band $BAND] Template already exists: $TEMPLATE_COLLECTION (skipping rebuild)"
    else
      # Build new template
      TMP_NIGHTS_FILE="$(mktemp)"
      TEMP_FILES+=("$TMP_NIGHTS_FILE")
      printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TMP_NIGHTS_FILE"
      if ! run_or_dry ./scripts/pipeline/30_coadds.sh --nights-file "$TMP_NIGHTS_FILE" --band "$BAND" --tract "$TRACT" -j "$JOBS"; then
        log "[WARN] Template build failed for band $BAND"
        FAILED_TEMPLATE+=("$BAND")
        EXIT_CODE=1
        [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
        continue
      fi

      # Find latest run for this tract/band; be tolerant of output quirks
      TEMPLATE_COLLECTION="$(butler query-collections "$REPO" 2>/dev/null | awk '{print $1}' \
        | grep -E "templates/deep/tract${TRACT}/${BAND}(/.*)?$" | tail -n1 || true)"

      if [[ -z "$TEMPLATE_COLLECTION" ]]; then
        PARENT="templates/deep/tract${TRACT}/${BAND}"
        if butler query-collections "$REPO" 2>/dev/null | awk '{print $1}' | grep -qx "$PARENT"; then
          TEMPLATE_COLLECTION="$PARENT"
        else
          echo "ERROR: No template collection found for band $BAND, tract $TRACT"
          echo "       Expected pattern: templates/deep/tract${TRACT}/${BAND}"
          echo "       Run '30_coadds.sh' may have failed or created unexpected collection names"
          exit 2
        fi
      fi
      log "[band $BAND] Using template: $TEMPLATE_COLLECTION"
    fi
  fi

  for night in "${SCIENCE_NIGHTS[@]}"; do
    DIA_ARGS=(--night "$night" -j "$JOBS" --band "$BAND" --tract "$TRACT")
    [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
    if [[ -n "$TEMPLATE_COLLECTION" ]]; then
      DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
    else
      # Use auto-template if no specific template collection was built
      DIA_ARGS+=(--auto-template)
    fi
    if [[ -n "$BAD_SUB_THRESH" ]]; then
      DIA_ARGS+=(--bad-sub-threshold "$BAD_SUB_THRESH")
    fi
    if ! run_or_dry ./scripts/pipeline/40_diff_imaging.sh "${DIA_ARGS[@]}"; then
      log "[WARN] DIA failed for night $night band $BAND"
      FAILED_DIA+=("${night}/${BAND}")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
done

log "All bands complete."
if [[ "$CONTINUE_ON_ERROR" == "true" ]]; then
  [[ ${#FAILED_CALIBS[@]} -gt 0 ]] && log "Failed calibs: ${FAILED_CALIBS[*]}"
  [[ ${#FAILED_SCIENCE[@]} -gt 0 ]] && log "Failed science: ${FAILED_SCIENCE[*]}"
  [[ ${#FAILED_TEMPLATE[@]} -gt 0 ]] && log "Failed template builds: ${FAILED_TEMPLATE[*]}"
  [[ ${#FAILED_DIA[@]} -gt 0 ]] && log "Failed DIA: ${FAILED_DIA[*]}"
fi
exit $EXIT_CODE
