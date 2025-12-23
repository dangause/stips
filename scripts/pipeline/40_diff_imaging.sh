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
#
# Requirements:
#   1. Single-visit processing completed (20_science.sh)
#   2. Template coadds built (30_coadds.sh) OR external templates available

set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHT="${NIGHT:-}"
TEMPLATE_COLLECTION=""
AUTO_TEMPLATE=false
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

show_usage() {
  cat <<USAGE
Usage: $0 --night YYYYMMDD [options]

Run difference imaging pipeline for transient/variable detection.

Required:
  -n, --night YYYYMMDD      Night to process

Template Options (choose one):
  -t, --template COLLECTION Template coadd collection
  --auto-template           Auto-discover best template (searches templates/* and coadds/*)

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

USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)           NIGHT="${2:-}"; shift 2;;
    -t|--template)        TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --auto-template)      AUTO_TEMPLATE=true; shift 1;;
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
    -h|--help)            show_usage;;
    *) echo "Unknown arg: $1"; show_usage;;
  esac
done

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

if [[ "$PIPELINE_MODE" == "standalone" ]]; then
  PIPE="$OBS_NICKEL/pipelines/DIA.yaml"
  SUBSET="#dia-full"
else
  PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
  SUBSET="#difference-imaging"
fi

TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
DIA_SUBTRACT_CFG="$OBS_NICKEL/configs/dia/subtractImages.py"
DIA_DETECT_CFG="$OBS_NICKEL/configs/dia/detectAndMeasure.py"

SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
DIFF_PARENT="Nickel/runs/${NIGHT}/diff/${RUN_TS}"
DIFF_RUN="${DIFF_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

QG_FILE="$QG_DIR/diff_${NIGHT}_${RUN_TS}.qg"
QG_DOT="$QG_DIR/diff_${NIGHT}_${RUN_TS}.dot"
LOG_FILE="$LOGS_DIR/diff_${NIGHT}_${RUN_TS}.log"

echo "=== [40_diff_imaging] night=${NIGHT} @ ${RUN_TS} ==="
echo "[mode] Pipeline: $PIPELINE_MODE ($PIPE$SUBSET)"

########## LSST STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: Pipeline not found: $PIPE"; exit 2; }

########## INPUT SANITY ##########
# Find latest raw run for this night (needed for data ID queries)
RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }

echo "[inputs] RAW_RUN=$RAW_RUN"
echo "[inputs] CALIB=$CALIB_CHAIN"
echo "[inputs] REFCATS=$REFCATS_CHAIN"
echo "[inputs] SKYMAPS=$SKYMAPS_CHAIN"

########## TEMPLATE DISCOVERY ##########
if [[ "$AUTO_TEMPLATE" == "true" ]]; then
  echo ""
  echo "[template] Auto-discovering templates..."

  # Use metadata-based filtering if date exclusion requested
  if [[ -n "$EXCLUDE_DATES_START" && -n "$EXCLUDE_DATES_END" ]]; then
    echo "  Date filtering: excluding $EXCLUDE_DATES_START to $EXCLUDE_DATES_END"

    TEMPLATE_META_SCRIPT="$OBS_NICKEL/scripts/python/data/template_metadata.py"
    if [[ ! -f "$TEMPLATE_META_SCRIPT" ]]; then
      echo "ERROR: Template metadata script not found: $TEMPLATE_META_SCRIPT"
      echo "Cannot perform date-based template filtering."
      exit 2
    fi

    # Query templates using metadata
    QUERY_ARGS=(query --repo "$REPO" --exclude-start "$EXCLUDE_DATES_START" --exclude-end "$EXCLUDE_DATES_END")
    [[ -n "$BAND" ]] && QUERY_ARGS+=(--band "$BAND")
    [[ -n "$TRACT" ]] && QUERY_ARGS+=(--tract "$TRACT")

    TEMPLATE_CANDIDATES="$(/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$TEMPLATE_META_SCRIPT" "${QUERY_ARGS[@]}" 2>&1 | \
      grep -E '^\s+templates/' | awk '{print $1}' || true)"

    if [[ -z "$TEMPLATE_CANDIDATES" ]]; then
      echo ""
      echo "ERROR: No templates found matching date exclusion criteria"
      echo ""
      echo "Available templates (use template_metadata.py list to see all):"
      /opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$TEMPLATE_META_SCRIPT" list --repo "$REPO" || true
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
    # Prioritize templates/* (purpose-built for DIA)
    TEMPLATE_CANDIDATES="$(butler query-collections "$REPO" 2>/dev/null | \
      awk '{print $1}' | \
      grep -E '^(templates|coadds)/' | \
      sort -r || true)"

    if [[ -z "$TEMPLATE_CANDIDATES" ]]; then
      echo ""
      echo "ERROR: No template collections found"
      echo ""
      echo "Available collections matching 'templates/' or 'coadds/':"
      butler query-collections "$REPO" | grep -E '^(templates|coadds)/' || echo "  (none)"
      echo ""
      echo "Build templates using:"
      echo "  1. scripts/pipeline/30_coadds.sh --nights-file NIGHTS --tract TRACT --band BAND"
      echo "  2. Or provide external templates via butler collection-chain"
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

    # Show candidates
    echo "  Candidates found:"
    echo "$TEMPLATE_CANDIDATES" | head -5 | sed 's/^/    /'
    if [[ $(echo "$TEMPLATE_CANDIDATES" | wc -l) -gt 5 ]]; then
      echo "    ... ($(echo "$TEMPLATE_CANDIDATES" | wc -l) total)"
    fi
  fi

  # Select first (most recent or highest priority)
  TEMPLATE_COLLECTION="$(echo "$TEMPLATE_CANDIDATES" | head -n1)"
  echo "  → Selected: $TEMPLATE_COLLECTION"
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
  echo "[template] Using: $TEMPLATE_COLLECTION"
fi

# Verify template has data
TEMPLATE_COUNT="$(butler query-datasets "$REPO" template_coadd \
  --collections "$TEMPLATE_COLLECTION" 2>/dev/null | wc -l || echo "0")"

if [[ "$TEMPLATE_COUNT" -eq 0 ]]; then
  echo "ERROR: Template collection exists but contains no template_coadd datasets"
  echo "Collection: $TEMPLATE_COLLECTION"
  exit 2
fi

echo "[template] Found $TEMPLATE_COUNT template coadds in $TEMPLATE_COLLECTION"

########## FIND SCIENCE PARENT RUN ##########
# Need to find the science processing run with preliminary_visit_image
# This is the input to DIA pipeline
echo ""
echo "[science] Finding science processing run for night ${NIGHT}..."

SCI_PARENT="$(butler query-collections "$REPO" 2>/dev/null | \
  awk '{print $1}' | \
  grep -E "^Nickel/runs/${NIGHT}/(processCcd|science)/" | \
  tail -n1 || true)"

if [[ -z "$SCI_PARENT" ]]; then
  echo "ERROR: No science processing run found for night ${NIGHT}"
  echo ""
  echo "Available runs for this night:"
  butler query-collections "$REPO" | grep "Nickel/runs/${NIGHT}/" || echo "  (none)"
  echo ""
  echo "Run science processing first:"
  echo "  scripts/pipeline/20_science.sh --night ${NIGHT}"
  echo ""
  exit 2
fi

echo "[science] Using: $SCI_PARENT"

# Verify science run has required datasets
if ! butler query-datasets "$REPO" preliminary_visit_image \
  --collections "$SCI_PARENT" \
  --where "instrument='Nickel' AND day_obs=${NIGHT}" 2>/dev/null | head -1 | grep -q .; then
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

########## TRACT/BAND FILTER ##########
SPATIAL_EXPR=""
if [[ -n "$TRACT" ]]; then
  SPATIAL_EXPR=" AND tract=${TRACT}"
  echo "[tract filter] ${TRACT}"
fi
if [[ -n "$BAND" ]]; then
  SPATIAL_EXPR="${SPATIAL_EXPR} AND band='${BAND}'"
  echo "[band filter] ${BAND}"
fi

########## BUILD DATA ID QUERY ##########
DATA_ID_QUERY="instrument='Nickel' AND exposure.observation_type='science' AND day_obs=${NIGHT}${OBJECT_EXPR}${BAD_EXPR}${SPATIAL_EXPR}"

echo ""
echo "[where] $DATA_ID_QUERY"
echo ""

########## GENERATE QUANTUM GRAPH ##########
echo "[qgraph] Generating quantum graph -> $QG_FILE"

# Build config options
CONFIG_OPTS=()
if [[ -f "$TUNED_CFG_FILE" ]]; then
  CONFIG_OPTS+=("--config-file" "calibrateImage:${TUNED_CFG_FILE}")
fi
if [[ -f "$DIA_SUBTRACT_CFG" ]]; then
  CONFIG_OPTS+=("--config-file" "subtractImages:${DIA_SUBTRACT_CFG}")
fi
if [[ -f "$DIA_DETECT_CFG" ]]; then
  CONFIG_OPTS+=("--config-file" "detectAndMeasureDiaSource:${DIA_DETECT_CFG}")
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
  -d "$DATA_ID_QUERY"; then
  echo "[ERROR] Quantum graph generation failed"
  echo ""
  echo "Common issues:"
  echo "  1. No exposures match the query (check day_obs, object filter, exclusions)"
  echo "  2. Template doesn't cover the tract/patch of your science exposures"
  echo "  3. Missing preliminary_visit_image in science run"
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
echo "[run] Running difference imaging pipeline (jobs=${JOBS})..."
echo "      Log: $LOG_FILE"
echo ""

if pipetask run \
    -b "$REPO" \
    -g "$QG_FILE" \
    --register-dataset-types \
    -j "$JOBS" \
    2>&1 | tee "$LOG_FILE"; then

  # Create/update collection chain
  butler collection-chain "$REPO" "$DIFF_PARENT" "$DIFF_RUN" --mode redefine >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$DIFF_PARENT" "$DIFF_RUN"

  echo ""
  echo "================================================================================"
  echo "=== [40_diff_imaging] SUCCESS ==="
  echo "================================================================================"
  echo "Night:               $NIGHT"
  echo "Template:            $TEMPLATE_COLLECTION"
  echo "DIA collection:      $DIFF_RUN"
  echo "DIA parent:          $DIFF_PARENT"
  echo ""

  # Query and show created datasets
  echo "[outputs] Difference images:"
  DIFF_IMG_COUNT="$(butler query-datasets "$REPO" difference_image \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${NIGHT}" \
    2>/dev/null | wc -l || echo "0")"
  echo "  → Created $DIFF_IMG_COUNT difference images"

  echo ""
  echo "[outputs] DIA sources detected:"
  DIA_SRC_COUNT="$(butler query-datasets "$REPO" dia_source_unfiltered \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${NIGHT}" \
    2>/dev/null | wc -l || echo "0")"
  echo "  → Created $DIA_SRC_COUNT DIA source catalogs"

  # Show sample of DIA sources
  echo ""
  echo "Sample DIA source catalogs:"
  butler query-datasets "$REPO" dia_source_unfiltered \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${NIGHT}" \
    2>/dev/null | head -5 | sed 's/^/  /' || true

  echo ""
  echo "================================================================================"
  echo "Next steps:"
  echo ""
  echo "1. INSPECT DIFFERENCE IMAGES (visual QA)"
  echo "   Use DS9 or Firefly to view difference images and check quality"
  echo ""
  echo "2. EXTRACT LIGHT CURVE for specific transient/variable:"
  echo "   By coordinates:"
  echo "     python scripts/python/data/extract_lightcurve.py \\"
  echo "       --repo \$REPO \\"
  echo "       --collection '$DIFF_RUN' \\"
  echo "       --ra YOUR_RA --dec YOUR_DEC \\"
  echo "       --radius 1.0 \\"
  echo "       --output lightcurve.csv"
  echo ""
  echo "   By object name (requires SIMBAD/NED):"
  echo "     python scripts/python/data/extract_lightcurve.py \\"
  echo "       --repo \$REPO \\"
  echo "       --collection '$DIFF_RUN' \\"
  echo "       --object 'AT2024abc' \\"
  echo "       --output lightcurve_AT2024abc.csv"
  echo ""
  echo "3. ASSESS DIA QUALITY:"
  echo "   Check logs for warnings: $LOG_FILE"
  echo "   Query DIA metrics:"
  echo "     butler query-datasets \$REPO \\"
  echo "       --collections '$DIFF_RUN' \\"
  echo "       difference_image"
  echo ""
  echo "4. MULTI-NIGHT PROCESSING:"
  echo "   Process more nights and combine light curves across dates"
  echo "================================================================================"
  echo ""

else
  echo ""
  echo "[ERROR] Difference imaging failed; see log: $LOG_FILE"
  echo ""
  echo "Common failure modes:"
  echo "  1. Template/science PSF mismatch (check seeing in both)"
  echo "  2. WCS alignment issues (check astrometry in science processing)"
  echo "  3. Insufficient kernel stars for PSF matching"
  echo "  4. Memory issues (try reducing -j/--jobs)"
  echo ""
  exit 2
fi
