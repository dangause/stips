#!/usr/bin/env bash
# 40_diff_imaging.sh — Production Difference Imaging Pipeline
#
# This script performs image subtraction using deep template coadds and generates
# DIA (Difference Image Analysis) source catalogs for transient/variable detection.
#
# Features:
#   - Automatic template discovery (finds best template for each visit/band)
#   - Support for both DIA.yaml (standalone) and DRP.yaml#difference-imaging
#   - Quality metrics and source counting
#   - Light curve extraction guidance
#   - Hierarchical logging system
#
# Requirements:
#   1. Single-visit processing completed (20_science.sh)
#   2. Template coadds built (30_coadds.sh) OR external templates available

# set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Source logging utilities
source "$(dirname "$0")/../utilities/logging.sh"

########## CLI ##########
NIGHT="${NIGHT:-}"
TEMPLATE_COLLECTION=""
AUTO_TEMPLATE=false
PREFER_PS1=false
EXCLUDE_DATES_START=""
EXCLUDE_DATES_END=""
BAD_EXPOSURES=""
BAD_EXPOSURES_FILE=""
OBJECT_FILTER=""
TRACT=""
BAND=""
JOBS="${JOBS:-8}"
PIPELINE_MODE="standalone"  # standalone (DIA.yaml) or integrated (DRP.yaml#difference-imaging)
FORCE_REPROCESS=false
BAD_SUB_THRESH=""
CONFIG_OVERRIDES=()
USE_SUBTRACT_TEST=false
DIA_SUBTRACT_CFG_OVERRIDE=""

show_usage() {
  cat <<USAGE
Usage: $0 --night YYYYMMDD [options]

Run difference imaging pipeline for transient/variable detection.

Required:
  -n, --night YYYYMMDD      Observing night to process (local date, e.g., 20210721)
                            Note: Uses observing_day dimension, not UT date

Template Options (choose one):
  -t, --template COLLECTION Template coadd collection
  --auto-template           Auto-discover best template (searches templates/* and coadds/*)
  --prefer-ps1              Prefer PS1 templates over internal templates (with --auto-template)

Template Date Filtering (for transient campaigns):
  --exclude-start YYYYMMDD  Exclude templates overlapping this start date
  --exclude-end YYYYMMDD    Exclude templates overlapping this end date
                            (Use both to avoid templates contaminated by transient)

Optional:
  --tract TRACT             Limit to specific tract (default: all)
  --band BAND               Limit to specific band (b/v/r/i, default: all)
  --object NAME             Filter by OBJECT header value (e.g., '2020wnt')
  --bad EXP_IDS             Comma-separated exposure/visit IDs to exclude
  --bad-file FILE           File with exposure IDs to exclude
  -j, --jobs N              Number of parallel jobs (default: ${JOBS})
  --pipeline MODE           Pipeline mode: standalone (DIA.yaml) or integrated (DRP.yaml)
  --force-reprocess         Force reprocessing of visit images (slower)
  --bad-sub-threshold NUM   Override badSubtractionRatioThreshold (default task value is 0.2)
  --subtract-config FILE    Extra subtractImages config override (applied after base config)
  --subtract-test           Use configs/dia/subtractImages_test.py override
  --config KEY=VAL          Extra pipetask config override (repeatable, e.g.
                            --config subtractImages:makeKernel.minKernelSources=1)

Examples:
  # Auto-discover template (recommended)
  $0 --night 20240625 --auto-template

  # Use specific template
  $0 --night 20240625 --template templates/deep/r

  # Process only one object in r-band
  $0 --night 20240625 --auto-template --object "2020wnt" --band r

  # Exclude templates from supernova campaign (Feb 19-28, 2021)
  $0 --night 20240625 --auto-template \\
    --exclude-start 20210219 --exclude-end 20210228

  # Use integrated DRP pipeline
  $0 --night 20240625 --auto-template --pipeline integrated

  # Relax bad subtraction threshold when residuals are high (e.g., 0.5)
  $0 --night 20240625 --auto-template --bad-sub-threshold 0.5

  # Apply conservative subtractImages overrides for ringing tests
  $0 --night 20240625 --auto-template --subtract-test

USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)           NIGHT="${2:-}"; shift 2;;
    -t|--template)        TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --auto-template)      AUTO_TEMPLATE=true; shift 1;;
    --prefer-ps1)         PREFER_PS1=true; shift 1;;
    --exclude-start)      EXCLUDE_DATES_START="${2:-}"; shift 2;;
    --exclude-end)        EXCLUDE_DATES_END="${2:-}"; shift 2;;
    --tract)              TRACT="${2:-}"; shift 2;;
    --band)               BAND="${2:-}"; shift 2;;
    --object)             OBJECT_FILTER="${2:-}"; shift 2;;
    --bad)                BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)           BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    -j|--jobs)            JOBS="${2:-}"; shift 2;;
    --pipeline)           PIPELINE_MODE="${2:-}"; shift 2;;
    --force-reprocess)    FORCE_REPROCESS=true; shift 1;;
    --bad-sub-threshold)  BAD_SUB_THRESH="${2:-}"; shift 2;;
    --subtract-config)    DIA_SUBTRACT_CFG_OVERRIDE="${2:-}"; shift 2;;
    --subtract-test)      USE_SUBTRACT_TEST=true; shift 1;;
    --config)             CONFIG_OVERRIDES+=("${2:-}"); shift 2;;
    -h|--help)            show_usage;;
    *) echo "Unknown arg: $1"; show_usage;;
  esac
done

# Validate config flag combinations
if [[ "$USE_SUBTRACT_TEST" == "true" && -n "$DIA_SUBTRACT_CFG_OVERRIDE" ]]; then
  echo "ERROR: Use only one of --subtract-test or --subtract-config"
  exit 2
fi

# Validate required args
[[ -n "$NIGHT" ]] || { echo "ERROR: --night required"; exit 2; }
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"; exit 2;
fi

# Validate pipeline mode
if [[ "$PIPELINE_MODE" != "standalone" && "$PIPELINE_MODE" != "integrated" ]]; then
  echo "ERROR: Invalid --pipeline mode: '$PIPELINE_MODE' (must be 'standalone' or 'integrated')";
  exit 2;
fi

# Validate bad subtraction threshold (float > 0) if provided
if [[ -n "$BAD_SUB_THRESH" ]]; then
  if ! [[ "$BAD_SUB_THRESH" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "ERROR: --bad-sub-threshold must be a positive number";
    exit 2;
  fi
  echo "[config] badSubtractionRatioThreshold=${BAD_SUB_THRESH} (detectAndMeasureDiaSource)"
fi

# Template discovery validation
if [[ "$AUTO_TEMPLATE" == "false" && -z "$TEMPLATE_COLLECTION" ]]; then
  echo "ERROR: Must specify either --template or --auto-template"
  show_usage
fi

if [[ "$AUTO_TEMPLATE" == "true" && -n "$TEMPLATE_COLLECTION" ]]; then
  echo "ERROR: Cannot use both --template and --auto-template"
  exit 2
fi

# Date exclusion validation
if [[ -n "$EXCLUDE_DATES_START" && -z "$EXCLUDE_DATES_END" ]]; then
  echo "ERROR: --exclude-start requires --exclude-end"
  exit 2
fi
if [[ -n "$EXCLUDE_DATES_END" && -z "$EXCLUDE_DATES_START" ]]; then
  echo "ERROR: --exclude-end requires --exclude-start"
  exit 2
fi
if [[ -n "$EXCLUDE_DATES_START" && "$AUTO_TEMPLATE" == "false" ]]; then
  echo "WARNING: --exclude-start/--exclude-end only used with --auto-template"
fi

########## ENVIRONMENT ##########
INSTRUMENT="lsst.obs.nickel.Nickel"

# Some Conda deactivate hooks expect this to be defined; keep empty if unset.
export RUBIN_EUPS_PATH="${RUBIN_EUPS_PATH:-}"

if [[ "$PIPELINE_MODE" == "standalone" ]]; then
  PIPE="$OBS_NICKEL/pipelines/DIA.yaml"
  SUBSET="#dia-full"
else
  PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
  SUBSET="#difference-imaging"
fi

TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
DIA_SUBTRACT_CFG="$OBS_NICKEL/configs/dia/subtractImages.py"
DIA_SUBTRACT_TEST_CFG="$OBS_NICKEL/configs/dia/subtractImages_test.py"
DIA_DETECT_CFG="$OBS_NICKEL/configs/dia/detectAndMeasure.py"

if [[ "$USE_SUBTRACT_TEST" == "true" ]]; then
  DIA_SUBTRACT_CFG_OVERRIDE="$DIA_SUBTRACT_TEST_CFG"
fi

SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
CALIB_CHAIN="${CALIB_CHAIN:-Nickel/calib/current}"
REFCATS_CHAIN="${REFCATS_CHAIN:-refcats}"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
DIFF_PARENT="Nickel/runs/${NIGHT}/diff/${RUN_TS}"
DIFF_RUN="${DIFF_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"

QG_FILE="$QG_DIR/diff_${NIGHT}_${RUN_TS}.qg"
QG_DOT="$QG_DIR/diff_${NIGHT}_${RUN_TS}.dot"

# Setup logging (creates LOG_DIR and LOG_FILE)
setup_logging "dia" "$NIGHT" "$BAND"

# Redirect all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Difference Imaging Pipeline"
log_info "Night: $NIGHT"
log_info "Band: ${BAND:-all}"
log_info "Pipeline mode: $PIPELINE_MODE ($PIPE$SUBSET)"
log_info "RUN_TS: $RUN_TS"
log_info "subtractImages config: $DIA_SUBTRACT_CFG"
if [[ -n "$DIA_SUBTRACT_CFG_OVERRIDE" ]]; then
  log_info "subtractImages override: $DIA_SUBTRACT_CFG_OVERRIDE"
fi
log_info "detectAndMeasureDiaSource config: $DIA_DETECT_CFG"

########## LSST STACK ##########
cd "$STACK_DIR"
set +u  # Temporarily disable unbound variable check for conda activation
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
set -u  # Re-enable unbound variable check
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: Pipeline not found: $PIPE"; exit 2; }

########## OBSERVING NIGHT → UT DAY_OBS CONVERSION ##########
# NIGHT variable is observing night (local date when observations began)
# DAY_OBS is UT date in FITS headers (typically obs_night + 1 day for CA observations)
# Collections are organized by observing night, but Butler queries use day_obs
obs_night_to_day_obs() {
  local obs_night="$1"
  # Use Python date arithmetic (obs_night + 1 day)
  python3 -c "from datetime import datetime, timedelta; dt = datetime.strptime('$obs_night', '%Y%m%d'); print((dt + timedelta(days=1)).strftime('%Y%m%d'))"
}

DAY_OBS="$(obs_night_to_day_obs "$NIGHT")"
log_info "Observing night (local): $NIGHT"
log_info "UT day_obs (FITS header): $DAY_OBS"

########## INPUT SANITY ##########
log_section "Input Collection Discovery"

# Find raw collection for this observing night (optional - DIA doesn't actually need it)
# Collections are named by observing night: Nickel/raw/YYYYMMDD/timestamp
RAW_RUN="$(butler query-collections "$REPO" 2>/dev/null | \
  awk '{print $1}' | \
  grep -E "^Nickel/raw/${NIGHT}/" | \
  tail -n1 || true)"

if [[ -n "$RAW_RUN" ]]; then
  log_info "Raw collection: $RAW_RUN"
else
  log_info "Raw collection: (none - using processed data only)"
fi
log_info "Calibs: $CALIB_CHAIN"
log_info "Refcats: $REFCATS_CHAIN"
log_info "Skymaps: $SKYMAPS_CHAIN"

########## TEMPLATE DISCOVERY ##########
log_section "Template Discovery"

if [[ "$AUTO_TEMPLATE" == "true" ]]; then
  log_info "Auto-discovering templates..."

  # Use metadata-based filtering if date exclusion requested
  if [[ -n "$EXCLUDE_DATES_START" && -n "$EXCLUDE_DATES_END" ]]; then
    echo "  Date filtering: excluding $EXCLUDE_DATES_START to $EXCLUDE_DATES_END"

    TEMPLATE_META_SCRIPT="$OBS_NICKEL/scripts/python/pipeline_tools/template_metadata.py"
    if [[ ! -f "$TEMPLATE_META_SCRIPT" ]]; then
      echo "ERROR: Template metadata script not found: $TEMPLATE_META_SCRIPT"
      echo "Cannot perform date-based template filtering."
      exit 2
    fi

    # Query templates using metadata
    QUERY_ARGS=(query --repo "$REPO" --exclude-start "$EXCLUDE_DATES_START" --exclude-end "$EXCLUDE_DATES_END")
    [[ -n "$BAND" ]] && QUERY_ARGS+=(--band "$BAND")
    [[ -n "$TRACT" ]] && QUERY_ARGS+=(--tract "$TRACT")

    CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
    TEMPLATE_CANDIDATES="$(/opt/anaconda3/envs/${CONDA_ENV}/bin/python "$TEMPLATE_META_SCRIPT" "${QUERY_ARGS[@]}" 2>&1 | \
      grep -E '^\s+templates/' | awk '{print $1}' || true)"

    if [[ -z "$TEMPLATE_CANDIDATES" ]]; then
      echo ""
      echo "ERROR: No templates found matching date exclusion criteria"
      echo ""
      echo "Available templates (use template_metadata.py list to see all):"
      /opt/anaconda3/envs/${CONDA_ENV}/bin/python "$TEMPLATE_META_SCRIPT" list --repo "$REPO" || true
      echo ""
      echo "Options:"
      echo "  1. Build templates from different date range"
      echo "  2. Relax date exclusion criteria"
      echo "  3. Use specific template with --template option"
      echo ""
      exit 2
    fi

    echo "  Metadata-filtered candidates:"
    echo "$TEMPLATE_CANDIDATES" | sed 's/^/    /'

  else
    # Standard discovery (no date filtering)
    # Search for template collections (both templates/* and coadds/*)

    # Determine search priority based on --prefer-ps1 flag
    if [[ "$PREFER_PS1" == "true" ]]; then
      # Prioritize PS1 templates
      SEARCH_PATTERN="^(templates/ps1|templates/deep|templates|coadds)/"
      echo "  Searching with PS1 preference..."
    else
      # Prioritize internally-built templates (standard behavior)
      SEARCH_PATTERN="^(templates/deep|templates|coadds)/"
      echo "  Searching with internal template preference..."
    fi

    TEMPLATE_CANDIDATES="$(butler query-collections "$REPO" 2>/dev/null | \
      awk '{print $1}' | \
      grep -E "$SEARCH_PATTERN" | \
      sort -r || true)"

    if [[ -z "$TEMPLATE_CANDIDATES" ]]; then
      echo ""
      echo "ERROR: No template collections found"
      echo ""
      echo "Available collections matching 'templates/' or 'coadds/':"
      butler query-collections "$REPO" | grep -E '^(templates|coadds)/' || echo "  (none)"
      echo ""
      echo "Build templates using:"
      echo "  1. Internal: scripts/pipeline/30_coadds.sh --nights-file NIGHTS --tract TRACT --band BAND"
      echo "  2. PS1: scripts/pipeline/08_ingest_ps1_template.sh --ra RA --dec DEC --band BAND"
      echo "  3. Or provide external templates via butler collection-chain"
      echo ""
      exit 2
    fi

    # Filter by band if specified
    if [[ -n "$BAND" ]]; then
      TEMPLATE_CANDIDATES="$(echo "$TEMPLATE_CANDIDATES" | grep "/$BAND\$" || true)"
      if [[ -z "$TEMPLATE_CANDIDATES" ]]; then
        echo "ERROR: No templates found for band '$BAND'"
        exit 2
      fi
    fi

    # Apply PS1 preference logic
    if [[ "$PREFER_PS1" == "true" ]]; then
      # Try to find PS1 template first
      PS1_TEMPLATE="$(echo "$TEMPLATE_CANDIDATES" | grep "templates/ps1/" | head -n1 || true)"
      if [[ -n "$PS1_TEMPLATE" ]]; then
        TEMPLATE_COLLECTION="$PS1_TEMPLATE"
        echo "  → Using PS1 template (--prefer-ps1): $TEMPLATE_COLLECTION"
      else
        # Fall back to internal templates
        TEMPLATE_COLLECTION="$(echo "$TEMPLATE_CANDIDATES" | head -n1)"
        echo "  → No PS1 templates found, using internal: $TEMPLATE_COLLECTION"
      fi
    else
      # Standard priority: internal templates first
      INTERNAL_TEMPLATE="$(echo "$TEMPLATE_CANDIDATES" | grep -E "templates/deep/" | head -n1 || true)"
      if [[ -n "$INTERNAL_TEMPLATE" ]]; then
        TEMPLATE_COLLECTION="$INTERNAL_TEMPLATE"
      else
        TEMPLATE_COLLECTION="$(echo "$TEMPLATE_CANDIDATES" | head -n1)"
      fi
    fi

    # Show candidates
    echo "  Candidates found:"
    echo "$TEMPLATE_CANDIDATES" | head -5 | sed 's/^/    /'
    if [[ $(echo "$TEMPLATE_CANDIDATES" | wc -l) -gt 5 ]]; then
      echo "    ... ($(echo "$TEMPLATE_CANDIDATES" | wc -l) total)"
    fi
    echo "  → Selected: $TEMPLATE_COLLECTION"
  fi
else
  # Verify user-provided template exists
  if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$TEMPLATE_COLLECTION"; then
    echo "ERROR: Template collection not found: $TEMPLATE_COLLECTION"
    echo ""
    echo "Available template collections:"
    butler query-collections "$REPO" | grep -E '^(templates|coadds)/' || echo "  (none found)"
    echo ""
    exit 2
  fi
  log_info "Using template: $TEMPLATE_COLLECTION"
fi

# Verify template has data
TEMPLATE_COUNT="$(butler query-datasets "$REPO" template_coadd \
  --collections "$TEMPLATE_COLLECTION" 2>/dev/null | wc -l || echo "0")"

if [[ "$TEMPLATE_COUNT" -eq 0 ]]; then
  echo "ERROR: Template collection exists but contains no template_coadd datasets"
  echo "Collection: $TEMPLATE_COLLECTION"
  exit 2
fi

log_info "Found $TEMPLATE_COUNT template coadds in $TEMPLATE_COLLECTION"

########## FIND SCIENCE PARENT RUN ##########
# Need to find the science processing run with preliminary_visit_image
# This is the input to DIA pipeline
echo ""
log_info "Finding science processing run for observing night $NIGHT..."

# Science runs are organized by observing night: Nickel/runs/YYYYMMDD/processCcd/...
SCI_PARENT="$(butler query-collections "$REPO" 2>/dev/null | \
  awk '{print $1}' | \
  grep -E "^Nickel/runs/${NIGHT}/(processCcd|science)/" | \
  tail -n1 || true)"

if [[ -z "$SCI_PARENT" ]]; then
  echo "ERROR: No science processing run found for observing night ${NIGHT}"
  echo ""
  echo "Available runs for this night:"
  butler query-collections "$REPO" 2>/dev/null | grep "Nickel/runs/${NIGHT}/" || echo "  (none)"
  echo ""
  echo "Run science processing first:"
  echo "  scripts/pipeline/20_science.sh --night ${NIGHT}"
  echo ""
  exit 2
fi

log_info "Using science collection: $SCI_PARENT"

# Verify science run has required datasets
if ! butler query-datasets "$REPO" preliminary_visit_image \
  --collections "$SCI_PARENT" \
  --where "instrument='Nickel'" 2>/dev/null | tail -n +2 | head -1 | grep -q .; then
  echo "ERROR: Science run $SCI_PARENT has no preliminary_visit_image datasets"
  echo "Re-run science processing:"
  echo "  scripts/pipeline/20_science.sh --night ${NIGHT}"
  exit 2
fi

########## EXCLUSIONS ##########
BAD_LIST="$BAD_EXPOSURES"
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  BAD_LIST="$BAD_LIST
$(cat "$BAD_EXPOSURES_FILE")"
fi

BAD_EXP_CSV="$(
  printf "%s\n" "$BAD_LIST" | sed -E 's/#.*//; s/[^0-9]+/\n/g' \
  | awk 'NF' | sort -n -u | paste -sd, -
)"
BAD_EXPR=""
[[ -n "$BAD_EXP_CSV" ]] && BAD_EXPR=" AND NOT (exposure IN (${BAD_EXP_CSV}) OR visit IN (${BAD_EXP_CSV}))"

[[ -n "$BAD_EXP_CSV" ]] && echo "[exclude] exposure/visit: ${BAD_EXP_CSV}" || echo "[exclude] none"

########## OBJECT FILTER ##########
OBJECT_EXPR=""
if [[ -n "$OBJECT_FILTER" ]]; then
  OBJECT_EXPR=" AND exposure.target_name='${OBJECT_FILTER}'"
  echo "[object filter] ${OBJECT_FILTER}"
else
  echo "[object filter] none (processing all science exposures)"
fi

########## BAND FILTER ##########
BAND_EXPR=""
if [[ -n "$BAND" ]]; then
  BAND_EXPR=" AND band='${BAND}'"
  echo "[band filter] ${BAND}"
fi

# Tract filter - note: tract is NOT included in the data ID query because
# preliminary_visit_image doesn't have tract dimension. The tract filter is
# applied via template collection selection and spatial matching.
if [[ -n "$TRACT" ]]; then
  echo "[tract filter] ${TRACT} (applied via template selection, not data query)"
fi

########## BUILD DATA ID QUERY ##########
# NOTE: Use DAY_OBS (UT date from FITS headers) for Butler queries
# Observing night 20201207 (local) has day_obs=20201208 (UT) in FITS headers
# NOTE: Do NOT include tract in query - preliminary_visit_image doesn't have tract dimension
DATA_ID_QUERY="instrument='Nickel' AND exposure.observation_type='science' AND day_obs=${DAY_OBS}${OBJECT_EXPR}${BAD_EXPR}${BAND_EXPR}"

log_section "Quantum Graph Generation"
log_info "WHERE clause: $DATA_ID_QUERY"

# Create quantum graph log
QUANTUM_LOG="$(get_task_log "quantum")"
log_info "Quantum graph log: $QUANTUM_LOG"

# Build config options
CONFIG_OPTS=()
# Note: calibrateImage config is not needed for DIA pipeline (only for processCcd)
if [[ -f "$DIA_SUBTRACT_CFG" ]]; then
  CONFIG_OPTS+=("--config-file" "subtractImages:${DIA_SUBTRACT_CFG}")
fi
if [[ -n "$DIA_SUBTRACT_CFG_OVERRIDE" ]]; then
  if [[ ! -f "$DIA_SUBTRACT_CFG_OVERRIDE" ]]; then
    echo "ERROR: subtractImages override config not found: $DIA_SUBTRACT_CFG_OVERRIDE"
    exit 2
  fi
  CONFIG_OPTS+=("--config-file" "subtractImages:${DIA_SUBTRACT_CFG_OVERRIDE}")
fi
if [[ -f "$DIA_DETECT_CFG" ]]; then
  CONFIG_OPTS+=("--config-file" "detectAndMeasureDiaSource:${DIA_DETECT_CFG}")
fi
if [[ -n "$BAD_SUB_THRESH" ]]; then
  CONFIG_OPTS+=("--config" "detectAndMeasureDiaSource:badSubtractionRatioThreshold=${BAD_SUB_THRESH}")
fi
# Guard for bash 3.2 + set -u (empty arrays trigger unbound errors)
if [[ ${CONFIG_OVERRIDES+x} && ${#CONFIG_OVERRIDES[@]} -gt 0 ]]; then
  for cfg in "${CONFIG_OVERRIDES[@]}"; do
    CONFIG_OPTS+=("--config" "$cfg")
  done
fi

if ! pipetask qgraph \
  -b "$REPO" \
  -p "${PIPE}${SUBSET}" \
  -i "$SCI_PARENT","$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN","$TEMPLATE_COLLECTION" \
  -o "$DIFF_PARENT" \
  --output-run "$DIFF_RUN" \
  --save-qgraph "$QG_FILE" \
  --qgraph-dot "$QG_DOT" \
  "${CONFIG_OPTS[@]}" \
  -d "$DATA_ID_QUERY" \
  2>&1 | tee "$QUANTUM_LOG"; then
  log_error "Quantum graph generation failed"
  echo ""
  echo "Common issues:"
  echo "  1. No exposures match the query (check observing_day=${NIGHT}, object filter, exclusions)"
  echo "  2. Template doesn't cover the tract/patch of your science exposures"
  echo "  3. Missing preliminary_visit_image in science run"
  echo "  4. observing_day dimension not populated (need to re-ingest data)"
  echo ""
  exit 2
fi

if [[ ! -s "$QG_FILE" ]]; then
  echo "[ERROR] Expected quantum graph not created: $QG_FILE"
  echo ""
  echo "Possible reasons:"
  echo "  1. No exposures match the query criteria"
  echo "  2. Template doesn't cover the tract/patch of your exposures"
  echo "  3. DIA tasks are not properly configured in $PIPE"
  echo ""
  exit 2
fi

# Show quantum graph summary
echo ""
pipetask qgraph -b "$REPO" -g "$QG_FILE" --show tasks 2>/dev/null || true
echo ""

########## RUN DIFFERENCE IMAGING ##########
log_section "Executing Pipeline"
log_info "Running difference imaging pipeline (jobs=$JOBS)"

if pipetask run \
    -b "$REPO" \
    -g "$QG_FILE" \
    --register-dataset-types \
    -j "$JOBS"; then

  # Create/update collection chain
  butler collection-chain "$REPO" "$DIFF_PARENT" "$DIFF_RUN" --mode redefine >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$DIFF_PARENT" "$DIFF_RUN"

  log_section "Output Summary"
  log_info "Night: $NIGHT"
  log_info "Template: $TEMPLATE_COLLECTION"
  log_info "DIA collection: $DIFF_RUN"
  log_info "DIA parent: $DIFF_PARENT"

  # Query and show created datasets
  DIFF_IMG_COUNT="$(butler query-datasets "$REPO" difference_image \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${DAY_OBS}" \
    2>/dev/null | tail -n +3 | wc -l || echo "0")"

  DIA_SRC_COUNT="$(butler query-datasets "$REPO" dia_source_unfiltered \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${DAY_OBS}" \
    2>/dev/null | tail -n +3 | wc -l || echo "0")"

  DIFF_IMG_COUNT="$(echo "$DIFF_IMG_COUNT" | xargs)"
  DIA_SRC_COUNT="$(echo "$DIA_SRC_COUNT" | xargs)"

  log_info "Difference images: $DIFF_IMG_COUNT"
  log_info "DIA source catalogs: $DIA_SRC_COUNT"

  # Write results summary file
  RESULTS_FILE="$LOG_DIR/results.txt"
  {
    echo "DIA Results Summary"
    echo "==================="
    echo ""
    echo "Night: $NIGHT"
    echo "Band: ${BAND:-all}"
    echo "UT day_obs: $DAY_OBS"
    echo "Template: $TEMPLATE_COLLECTION"
    echo ""
    echo "Outputs:"
    echo "  Difference images: $DIFF_IMG_COUNT"
    echo "  DIA sources: $DIA_SRC_COUNT"
    echo "  Collection: $DIFF_RUN"
    echo ""
    echo "Files:"
    echo "  Quantum graph: $QG_FILE"
    echo "  Log: $LOG_FILE"
  } > "$RESULTS_FILE"

  log_info "Results summary: $RESULTS_FILE"

  # Print final log summary
  print_log_summary

  log_section "DIA Processing Complete"
  exit 0

else
  log_error "Difference imaging failed"
  log_error "Check log: $LOG_FILE"
  echo ""
  echo "Common failure modes:"
  echo "  1. Template/science PSF mismatch (check seeing in both)"
  echo "  2. WCS alignment issues (check astrometry in science processing)"
  echo "  3. Insufficient kernel stars for PSF matching"
  echo "  4. Memory issues (try reducing -j/--jobs)"
  echo ""
  print_log_summary
  exit 2
fi
