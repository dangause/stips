#!/usr/bin/env bash
# 40_diff_imaging.sh — Difference imaging for transient/variable detection
#
# This script performs image subtraction using deep template coadds and generates
# DIA (Difference Image Analysis) source catalogs for light curve extraction.

# set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHT="${NIGHT:-}"
TEMPLATE_COLLECTION=""
BAD_EXPOSURES=""
BAD_EXPOSURES_FILE=""
OBJECT_FILTER=""
TRACT=""
BAND=""
JOBS="${JOBS:-8}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)           NIGHT="${2:-}"; shift 2;;
    -t|--template)        TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --tract)              TRACT="${2:-}"; shift 2;;
    --band)               BAND="${2:-}"; shift 2;;
    --object)             OBJECT_FILTER="${2:-}"; shift 2;;
    --bad)                BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)           BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    -j|--jobs)            JOBS="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --night YYYYMMDD --template COLLECTION [options]

Run difference imaging pipeline for transient/variable detection.

Required:
  -n, --night YYYYMMDD      Night to process
  -t, --template COLLECTION Template coadd collection (from 30_coadds.sh)

Optional:
  --tract TRACT             Limit to specific tract (default: all)
  --band BAND               Limit to specific band (b/v/r/i, default: all)
  --object NAME             Filter by OBJECT header value (e.g., '2020wnt')
  --bad EXP_IDS             Comma-separated exposure/visit IDs to exclude
  --bad-file FILE           File with exposure IDs to exclude
  -j, --jobs N              Number of parallel jobs (default: ${JOBS})

Examples:
  # Run DIA on all exposures from a night
  $0 --night 20240625 --template templates/deep/tract1099/r

  # Process only exposures of a specific object
  $0 --night 20240625 --template templates/deep/tract1099/r --object "2020wnt"

  # Process specific band and tract
  $0 --night 20240625 --template templates/deep/tract1099/r --tract 1099 --band r

NOTE: This script expects the DIA tasks to be uncommented in DRP.yaml.
      If you see errors about missing tasks, edit pipelines/DRP.yaml and
      uncomment the difference-imaging section (lines ~205-252).
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Validate required args
[[ -n "$NIGHT" ]] || { echo "ERROR: --night required"; exit 2; }
[[ -n "$TEMPLATE_COLLECTION" ]] || { echo "ERROR: --template required"; exit 2; }
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"; exit 2;
fi

########## ENVIRONMENT ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
SCI_PARENT="Nickel/runs/${NIGHT}/processCcd/${RUN_TS}"
SCI_RUN="${SCI_PARENT}/run"
DIFF_PARENT="Nickel/runs/${NIGHT}/diff/${RUN_TS}"
DIFF_RUN="${DIFF_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

QG_FILE="$QG_DIR/diff_${NIGHT}_${RUN_TS}.qg"
QG_DOT="$QG_DIR/diff_${NIGHT}_${RUN_TS}.dot"
LOG_FILE="$LOGS_DIR/diff_${NIGHT}_${RUN_TS}.log"

echo "=== [40_diff_imaging] night=${NIGHT} @ ${RUN_TS} ==="

########## LSST STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: Pipeline not found: $PIPE"; exit 2; }

########## CHECK IF DIA TASKS ARE ENABLED ##########
if ! grep -q "^  reprocessVisitImage:" "$PIPE" 2>/dev/null; then
  echo ""
  echo "================================================================================"
  echo "ERROR: Difference imaging tasks are commented out in DRP.yaml"
  echo ""
  echo "To enable DIA, edit $PIPE"
  echo "and uncomment the following sections:"
  echo "  1. Lines ~205-252: DIA task definitions"
  echo "  2. Lines ~369-373: 'difference-imaging' subset"
  echo "  3. Lines ~388-389: 'difference-imaging' step"
  echo ""
  echo "Then re-run this script."
  echo "================================================================================"
  echo ""
  exit 2
fi

########## INPUT SANITY ##########
# Find latest raw run for this night
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }

# Verify template collection exists
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$TEMPLATE_COLLECTION"; then
  echo "ERROR: Template collection not found: $TEMPLATE_COLLECTION"
  echo ""
  echo "Available template collections:"
  butler query-collections "$REPO" | grep -E "^templates/" || echo "  (none found)"
  echo ""
  echo "Run 30_coadds.sh to build templates first."
  exit 2
fi

echo "[inputs] RAW_RUN=$RAW_RUN"
echo "[inputs] TEMPLATE=$TEMPLATE_COLLECTION"
echo "[inputs] CALIB=$CALIB_CHAIN"
echo "[inputs] REFCATS=$REFCATS_CHAIN"
echo "[inputs] SKYMAPS=$SKYMAPS_CHAIN"

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
DATA_ID_QUERY="instrument='Nickel' AND exposure.observation_type='science'${OBJECT_EXPR}${BAD_EXPR}${SPATIAL_EXPR}"

echo "[where] $DATA_ID_QUERY"

########## GENERATE QUANTUM GRAPH ##########
echo "[qgraph] Generating quantum graph -> $QG_FILE"

if ! pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#difference-imaging" \
  -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN","$TEMPLATE_COLLECTION" \
  -o "$DIFF_PARENT" \
  --output-run "$DIFF_RUN" \
  --save-qgraph "$QG_FILE" \
  --qgraph-dot "$QG_DOT" \
  --config-file "calibrateImage:${TUNED_CFG_FILE}" \
  -d "$DATA_ID_QUERY"; then
  echo "[ERROR] Quantum graph generation failed"
  exit 2
fi

if [[ ! -s "$QG_FILE" ]]; then
  echo "[ERROR] Expected quantum graph not created: $QG_FILE"
  echo ""
  echo "Possible reasons:"
  echo "  1. No exposures match the query criteria"
  echo "  2. Template doesn't cover the tract/patch of your exposures"
  echo "  3. DIA tasks are not properly configured in DRP.yaml"
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
  echo "=== [40_diff_imaging] SUCCESS ==="
  echo "Night:               $NIGHT"
  echo "Template:            $TEMPLATE_COLLECTION"
  echo "DIA collection:      $DIFF_RUN"
  echo "DIA parent:          $DIFF_PARENT"
  echo ""

  # Query and show created datasets
  echo "[outputs] Difference images created:"
  butler query-datasets "$REPO" difference_image \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${NIGHT}" \
    2>/dev/null | head -20 || true

  echo ""
  echo "[outputs] DIA sources detected:"
  butler query-datasets "$REPO" dia_source_unfiltered \
    --collections "$DIFF_RUN" \
    --where "instrument='Nickel' AND day_obs=${NIGHT}" \
    2>/dev/null | head -20 || true

  echo ""
  echo "================================================================================"
  echo "Next steps:"
  echo "  1. Inspect difference images visually"
  echo "  2. Extract light curve using scripts/extract_lightcurve.py"
  echo "     Example:"
  echo "       python scripts/extract_lightcurve.py \\"
  echo "         --repo \$REPO \\"
  echo "         --collection '$DIFF_RUN' \\"
  echo "         --ra YOUR_RA --dec YOUR_DEC \\"
  echo "         --output lightcurve.csv"
  echo "================================================================================"
  echo ""

else
  echo ""
  echo "[ERROR] Difference imaging failed; see log: $LOG_FILE"
  exit 2
fi
