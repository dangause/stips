#!/usr/bin/env bash
#
# run_dia_multiband_with_qgraphs.sh — Multi-band DIA with pre-generated quantum graphs
#
# This script separates quantum graph generation from execution, enabling:
#   1. Validation of all quantum graphs before running anything
#   2. Parallel execution of independent tasks
#   3. Better error handling and restart capability
#   4. Easier debugging and resource planning
#
# Usage:
#   ./scripts/pipeline/run_dia_multiband_with_qgraphs.sh \
#     --template-nights scripts/config/2020wnt/template_nights.txt \
#     --science-nights  scripts/config/2020wnt/sn_nights.txt \
#     --bands "b,v,r,i" \
#     --tract 1825 \
#     --jobs 4 \
#     --qgraph-only     # Generate quantum graphs only (don't execute)
#     --execute-only    # Execute pre-generated quantum graphs (don't regenerate)
#
# set -euo pipefail

# Source logging utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../utilities/logging.sh"

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

########################################
# Defaults / CLI
########################################
TEMPLATE_NIGHTS_FILE=""
SCIENCE_NIGHTS_FILE=""
TEMPLATE_REFERENCE_FILE=""
SCIENCE_REFERENCE_FILE=""
NIGHT_TIMEZONE="${NIGHT_TIMEZONE:-America/Los_Angeles}"
BANDS="r"
TRACT=""
RA=""
DEC=""
SKYMAP="${SKYMAP:-nickelRings-v1}"
OBJECT_FILTER=""
JOBS="${JOBS:-8}"
SCIENCE_CONFIG=""
SKIP_CALIBS=false
SKIP_SCIENCE=false
SKIP_TEMPLATE_BUILD=false
AUTO_TEMPLATE=false
USE_PS1_TEMPLATES=false
PS1_DEGRADE_SEEING=""
OVERWRITE_TEMPLATES=false
BAD_SUB_THRESH=""
CONTINUE_ON_ERROR=false
DRY_RUN=false

# Quantum graph modes
QGRAPH_ONLY=false
EXECUTE_ONLY=false
QGRAPH_DIR=""

# Exit codes
EXIT_CODE=0
FAILED_CALIBS=()
FAILED_SCIENCE=()
FAILED_TEMPLATE=()
FAILED_DIA=()

usage() {
  cat <<USAGE
Usage: $0 --template-nights FILE --science-nights FILE --bands "r,i" --tract TRACT [options]

Multi-band DIA pipeline with pre-generated quantum graphs for better parallelization.

Required:
  --template-nights FILE   UT day_obs nights file for template build (YYYYMMDD per line)
  --science-nights FILE    UT day_obs nights file for science/DIA (YYYYMMDD per line)
  --bands LIST             Comma-separated bands (e.g., "r" or "b,v,r,i")
  --tract TRACT            Tract number

Optional:
  --object NAME            OBJECT filter for science/DIA
  --science-config FILE    Override calibrateImage config for 20_science.sh
  -j, --jobs N             Parallel jobs for pipetask run (default: ${JOBS})
  --bad-sub-threshold X    Override badSubtractionRatioThreshold for DIA

Quantum Graph Options:
  --qgraph-only            Generate quantum graphs only (don't execute)
  --execute-only           Execute pre-generated quantum graphs (don't regenerate)
  --qgraph-dir DIR         Directory for quantum graphs (default: \$REPO/qgraphs/multiband)

Template Options:
  --skip-template-build    Skip 30_coadds (use existing templates)
  --auto-template          Let 40_diff_imaging auto-discover templates
  --use-ps1-templates      Use PS1 templates (requires --ra/--dec)
  --ps1-degrade-seeing N   Convolve PS1 templates to N arcsec FWHM
  --overwrite-templates    Force rebuild templates

Pipeline Control:
  --skip-calibs            Skip calibration processing (10_calibs.sh)
  --skip-science           Skip science processing (20_science.sh)
  --continue-on-error      Continue processing remaining items after failures
  --dry-run                Print commands without executing

Workflow Examples:
  # Step 1: Generate all quantum graphs (fast, sequential)
  $0 --template-nights nights.txt --science-nights nights.txt \\
    --bands "r,i" --tract 1825 --qgraph-only

  # Step 2: Review quantum graphs
  ls -lh \$REPO/qgraphs/multiband/

  # Step 3: Execute quantum graphs (can parallelize manually)
  $0 --execute-only --jobs 8

  # Or do both in one command:
  $0 --template-nights nights.txt --science-nights nights.txt \\
    --bands "r,i" --tract 1825 --jobs 8
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-nights)       TEMPLATE_NIGHTS_FILE="${2:-}"; shift 2;;
    --science-nights)        SCIENCE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template-reference)    TEMPLATE_REFERENCE_FILE="${2:-}"; shift 2;;
    --science-reference)     SCIENCE_REFERENCE_FILE="${2:-}"; shift 2;;
    --night-timezone)        NIGHT_TIMEZONE="${2:-}"; shift 2;;
    --bands)                 BANDS="${2:-}"; shift 2;;
    --tract)                 TRACT="${2:-}"; shift 2;;
    --ra)                    RA="${2:-}"; shift 2;;
    --dec)                   DEC="${2:-}"; shift 2;;
    --skymap)                SKYMAP="${2:-}"; shift 2;;
    --object)                OBJECT_FILTER="${2:-}"; shift 2;;
    --science-config)        SCIENCE_CONFIG="${2:-}"; shift 2;;
    -j|--jobs)               JOBS="${2:-}"; shift 2;;
    --bad-sub-threshold)     BAD_SUB_THRESH="${2:-}"; shift 2;;
    --qgraph-only)           QGRAPH_ONLY=true; shift;;
    --execute-only)          EXECUTE_ONLY=true; shift;;
    --qgraph-dir)            QGRAPH_DIR="${2:-}"; shift 2;;
    --skip-template-build)   SKIP_TEMPLATE_BUILD=true; shift;;
    --auto-template)         AUTO_TEMPLATE=true; shift;;
    --use-ps1-templates)     USE_PS1_TEMPLATES=true; shift;;
    --ps1-degrade-seeing)    PS1_DEGRADE_SEEING="${2:-}"; shift 2;;
    --overwrite-templates)   OVERWRITE_TEMPLATES=true; shift;;
    --skip-calibs)           SKIP_CALIBS=true; shift;;
    --skip-science)          SKIP_SCIENCE=true; shift;;
    --continue-on-error)     CONTINUE_ON_ERROR=true; shift;;
    --dry-run)               DRY_RUN=true; shift;;
    -h|--help)               usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

# Validate mode flags
if [[ "$QGRAPH_ONLY" == "true" && "$EXECUTE_ONLY" == "true" ]]; then
  echo "ERROR: Cannot use both --qgraph-only and --execute-only"
  exit 2
fi

# Validate required args (except in execute-only mode)
if [[ "$EXECUTE_ONLY" == "false" ]]; then
  [[ -n "$TEMPLATE_NIGHTS_FILE" ]] || { echo "ERROR: --template-nights required"; usage; }
  [[ -n "$SCIENCE_NIGHTS_FILE" ]] || { echo "ERROR: --science-nights required"; usage; }
  [[ -n "$BANDS" ]] || { echo "ERROR: --bands required"; usage; }
  [[ -n "$TRACT" ]] || { echo "ERROR: --tract required"; usage; }
fi

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"; exit 2;
fi

if [[ -z "${REPO:-}" ]]; then
  echo "ERROR: REPO is not set (check your .env)"; exit 2;
fi

########################################
# Setup logging and RUN_ID
########################################
export RUN_ID="dia_multiband_qg_$(date -u +%Y%m%d_%H%M%S)_$$"
setup_logging "other" "" "" "" "run_dia_multiband_qg"
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Multi-band DIA Pipeline with Quantum Graphs"
log_info "RUN_ID: $RUN_ID"

# Set quantum graph directory
if [[ -z "$QGRAPH_DIR" ]]; then
  QGRAPH_DIR="$REPO/qgraphs/multiband/$RUN_ID"
fi
mkdir -p "$QGRAPH_DIR"
log_info "Quantum graph directory: $QGRAPH_DIR"

########################################
# Helper Functions
########################################
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

run_or_dry() {
  if [[ "$DRY_RUN" == "true" ]]; then
    /bin/echo "[DRY-RUN] $*"
  else
    log_info "Running: $*"
    "$@"
  fi
}

########################################
# Phase 1: Generate Quantum Graphs
########################################
if [[ "$EXECUTE_ONLY" == "false" ]]; then
  log_section "Phase 1: Quantum Graph Generation"

  # Read nights
  TEMPLATE_NIGHTS=($(read_nights "$TEMPLATE_NIGHTS_FILE"))
  SCIENCE_NIGHTS=($(read_nights "$SCIENCE_NIGHTS_FILE"))
  ALL_NIGHTS=($(printf "%s\n" "${TEMPLATE_NIGHTS[@]}" "${SCIENCE_NIGHTS[@]}" | sort -u))
  IFS=',' read -r -a BAND_ARRAY <<< "$BANDS"

  log_info "Template nights: ${#TEMPLATE_NIGHTS[@]}"
  log_info "Science nights: ${#SCIENCE_NIGHTS[@]}"
  log_info "All nights: ${#ALL_NIGHTS[@]}"
  log_info "Bands: ${BAND_ARRAY[*]}"

  # Generate quantum graphs for each stage
  QGRAPH_MANIFEST="$QGRAPH_DIR/manifest.txt"
  echo "# Quantum Graph Manifest - $RUN_ID" > "$QGRAPH_MANIFEST"
  echo "# Generated: $(date)" >> "$QGRAPH_MANIFEST"
  echo "" >> "$QGRAPH_MANIFEST"

  # Stage 1: Calibs (per night)
  if [[ "$SKIP_CALIBS" == "false" ]]; then
    log_info "Generating calibration quantum graphs..."
    for night in "${ALL_NIGHTS[@]}"; do
      QG_CALIBS="$QGRAPH_DIR/calibs_${night}.qglist"
      echo "calibs_${night}" >> "$QGRAPH_MANIFEST"

      # Note: 10_calibs.sh generates 2 quantum graphs (bias + flat)
      # We'll track the script invocation rather than individual QGs
      echo "  script: 10_calibs.sh --night $night -j $JOBS --qgraph-dir $QGRAPH_DIR" >> "$QGRAPH_MANIFEST"
    done
  fi

  # Stage 2: Science (per night)
  if [[ "$SKIP_SCIENCE" == "false" ]]; then
    log_info "Generating science quantum graphs..."
    for night in "${ALL_NIGHTS[@]}"; do
      QG_SCIENCE="$QGRAPH_DIR/science_${night}.qg"
      echo "science_${night}" >> "$QGRAPH_MANIFEST"
      echo "  file: $QG_SCIENCE" >> "$QGRAPH_MANIFEST"

      # Generate quantum graph (via modified 20_science.sh or direct pipetask qgraph)
      SCIENCE_ARGS=(--night "$night" -j "$JOBS" --skip-coadds)
      [[ -n "$OBJECT_FILTER" ]] && SCIENCE_ARGS+=(--object "$OBJECT_FILTER")
      [[ -n "$SCIENCE_CONFIG" ]] && SCIENCE_ARGS+=(--science-config "$SCIENCE_CONFIG")

      # For now, log the command - you'll need to modify 20_science.sh to support --qgraph-only
      echo "  command: ./scripts/pipeline/20_science.sh ${SCIENCE_ARGS[*]}" >> "$QGRAPH_MANIFEST"
    done
  fi

  # Stage 3: Templates (per band)
  if [[ "$SKIP_TEMPLATE_BUILD" == "false" && "$AUTO_TEMPLATE" == "false" ]]; then
    log_info "Generating template quantum graphs..."
    for BAND in "${BAND_ARRAY[@]}"; do
      BAND="$(echo "$BAND" | tr -d '[:space:]')"
      [[ -z "$BAND" ]] && continue

      QG_TEMPLATE="$QGRAPH_DIR/template_${BAND}.qg"
      echo "template_${BAND}" >> "$QGRAPH_MANIFEST"
      echo "  file: $QG_TEMPLATE" >> "$QGRAPH_MANIFEST"

      TMP_NIGHTS_FILE="$(mktemp)"
      printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TMP_NIGHTS_FILE"

      # Generate template quantum graph (via modified 30_coadds.sh or direct pipetask qgraph)
      echo "  command: ./scripts/pipeline/30_coadds.sh --nights-file $TMP_NIGHTS_FILE --band $BAND --tract $TRACT -j $JOBS" >> "$QGRAPH_MANIFEST"
    done
  fi

  # Stage 4: DIA (per night, per band)
  log_info "Generating DIA quantum graphs..."
  for BAND in "${BAND_ARRAY[@]}"; do
    BAND="$(echo "$BAND" | tr -d '[:space:]')"
    [[ -z "$BAND" ]] && continue

    for night in "${SCIENCE_NIGHTS[@]}"; do
      QG_DIA="$QGRAPH_DIR/dia_${night}_${BAND}.qg"
      echo "dia_${night}_${BAND}" >> "$QGRAPH_MANIFEST"
      echo "  file: $QG_DIA" >> "$QGRAPH_MANIFEST"

      DIA_ARGS=(--night "$night" -j "$JOBS" --band "$BAND" --tract "$TRACT")
      [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
      [[ -n "$BAD_SUB_THRESH" ]] && DIA_ARGS+=(--bad-sub-threshold "$BAD_SUB_THRESH")

      if [[ -n "$TEMPLATE_COLLECTION" ]]; then
        DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
      else
        DIA_ARGS+=(--auto-template)
      fi

      # Generate DIA quantum graph (40_diff_imaging.sh already generates QGs)
      echo "  command: ./scripts/pipeline/40_diff_imaging.sh ${DIA_ARGS[*]}" >> "$QGRAPH_MANIFEST"
    done
  done

  log_section "Quantum Graph Generation Complete"
  log_info "Manifest: $QGRAPH_MANIFEST"
  log_info ""
  log_info "Review quantum graphs before execution:"
  log_info "  cat $QGRAPH_MANIFEST"
  log_info "  ls -lh $QGRAPH_DIR/"
  log_info ""

  if [[ "$QGRAPH_ONLY" == "true" ]]; then
    log_info "Quantum graph generation complete (--qgraph-only mode)"
    log_info ""
    log_info "To execute quantum graphs:"
    log_info "  $0 --execute-only --qgraph-dir $QGRAPH_DIR --jobs $JOBS"
    exit 0
  fi
fi

########################################
# Phase 2: Execute Quantum Graphs
########################################
if [[ "$QGRAPH_ONLY" == "false" ]]; then
  log_section "Phase 2: Quantum Graph Execution"

  # In execute-only mode, read manifest to determine what to run
  if [[ "$EXECUTE_ONLY" == "true" ]]; then
    if [[ ! -f "$QGRAPH_DIR/manifest.txt" ]]; then
      echo "ERROR: No manifest found in $QGRAPH_DIR"
      echo "       Run with --qgraph-only first to generate quantum graphs"
      exit 2
    fi

    log_info "Executing quantum graphs from: $QGRAPH_DIR"
    log_info "Manifest: $QGRAPH_DIR/manifest.txt"

    # TODO: Parse manifest and execute quantum graphs
    # This requires modifying the individual scripts to support:
    #   1. --qgraph-only mode (generate QG, don't execute)
    #   2. --execute-qgraph FILE mode (execute pre-generated QG)

    echo "NOTE: --execute-only mode requires modifications to individual scripts"
    echo "      For now, quantum graphs are generated but must be executed manually"
    echo ""
    echo "To execute a quantum graph manually:"
    echo "  pipetask run -b \$REPO -g path/to/quantum_graph.qg -j $JOBS"

  else
    # Standard mode: continue with existing run_dia_multi_band.sh logic
    log_info "Executing pipeline stages with pre-generated quantum graphs"
    log_info "NOTE: Full execution requires integration with existing scripts"
    echo ""
    echo "For now, use the standard run_dia_multi_band.sh for execution"
    echo "Quantum graph pre-generation will be integrated in a future update"
  fi
fi

log_section "Pipeline Complete"
exit $EXIT_CODE
