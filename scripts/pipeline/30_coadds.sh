#!/usr/bin/env bash
# 30_coadds.sh — Build deep multi-night coadd templates for difference imaging
#
# This script creates deep template coadds by stacking multiple nights of data.
# Use this to build reference templates for difference imaging / transient detection.

# set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHTS_FILE=""
NIGHTS_LIST=""
TRACT=""
BAND=""
PATCH=""
INPUT_COLLECTIONS=""
OUTPUT_COLLECTION=""
JOBS="${JOBS:-8}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nights-file)     NIGHTS_FILE="${2:-}"; shift 2;;
    --nights)          NIGHTS_LIST="${2:-}"; shift 2;;
    --tract)           TRACT="${2:-}"; shift 2;;
    --band)            BAND="${2:-}"; shift 2;;
    --patch)           PATCH="${2:-}"; shift 2;;
    -i|--input)        INPUT_COLLECTIONS="${2:-}"; shift 2;;
    -o|--output)       OUTPUT_COLLECTION="${2:-}"; shift 2;;
    -j|--jobs)         JOBS="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --tract TRACT --band BAND [options]

Build deep multi-night coadd templates for difference imaging.

Required:
  --tract TRACT             Tract ID to process (e.g., 1099)
  --band BAND               Band to process (b, v, r, i)

Optional:
  --nights-file FILE        File with list of nights (YYYYMMDD, one per line)
  --nights NIGHTS           Comma-separated list of nights (e.g., "20240625,20240626")
  --patch PATCH             Specific patch ID (default: all patches in tract)
  -i, --input COLLECTIONS   Input collections (default: auto-discover from nights)
  -o, --output COLLECTION   Output collection (default: templates/deep/{tract}/{band})
  -j, --jobs N              Number of parallel jobs (default: ${JOBS})

Examples:
  # Build r-band template for tract 1099 from all available nights
  $0 --tract 1099 --band r

  # Build template from specific nights
  $0 --tract 1099 --band r --nights "20240625,20240626,20240627"

  # Build template from nights listed in file
  $0 --tract 1099 --band r --nights-file good_nights.txt

  # Build single patch
  $0 --tract 1099 --band r --patch 88
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Validate required args
[[ -n "$TRACT" ]] || { echo "ERROR: --tract required"; exit 2; }
[[ -n "$BAND" ]] || { echo "ERROR: --band required"; exit 2; }
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"; exit 2;
fi

########## ENVIRONMENT ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

# Default output collection
if [[ -z "$OUTPUT_COLLECTION" ]]; then
  OUTPUT_COLLECTION="templates/deep/tract${TRACT}/${BAND}/${RUN_TS}"
fi
TEMPLATE_PARENT="templates/deep/tract${TRACT}/${BAND}"
TEMPLATE_RUN="${OUTPUT_COLLECTION}"

QG_FILE="$QG_DIR/template_t${TRACT}_${BAND}_${RUN_TS}.qg"
QG_DOT="$QG_DIR/template_t${TRACT}_${BAND}_${RUN_TS}.dot"
LOG_FILE="$LOGS_DIR/template_t${TRACT}_${BAND}_${RUN_TS}.log"

echo "=== [30_coadds] Building deep template: tract=${TRACT} band=${BAND} @ ${RUN_TS} ==="

########## LSST STACK ##########
# Save critical variables (LSST stack setup may clear them)
_SAVED_NIGHTS_FILE="$NIGHTS_FILE"
_SAVED_NIGHTS_LIST="$NIGHTS_LIST"
_SAVED_TRACT="$TRACT"
_SAVED_BAND="$BAND"
_SAVED_PATCH="$PATCH"
_SAVED_INPUT_COLLECTIONS="$INPUT_COLLECTIONS"
_SAVED_OUTPUT_COLLECTION="$OUTPUT_COLLECTION"
_SAVED_JOBS="$JOBS"

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Restore variables
NIGHTS_FILE="$_SAVED_NIGHTS_FILE"
NIGHTS_LIST="$_SAVED_NIGHTS_LIST"
TRACT="$_SAVED_TRACT"
BAND="$_SAVED_BAND"
PATCH="$_SAVED_PATCH"
INPUT_COLLECTIONS="$_SAVED_INPUT_COLLECTIONS"
OUTPUT_COLLECTION="$_SAVED_OUTPUT_COLLECTION"
JOBS="$_SAVED_JOBS"

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: Pipeline not found: $PIPE"; exit 2; }

########## BUILD INPUT COLLECTION LIST ##########
if [[ -n "$INPUT_COLLECTIONS" ]]; then
  # User provided explicit input collections
  INPUT_CHAIN="$INPUT_COLLECTIONS"
  echo "[input] Using provided collections: $INPUT_CHAIN"
else
  # Auto-discover from nights
  NIGHTS_ARRAY=()

  if [[ -n "$NIGHTS_FILE" && -f "$NIGHTS_FILE" ]]; then
    # Read from file
    while IFS= read -r line || [[ -n "$line" ]]; do
      night=$(echo "$line" | sed 's/#.*//' | tr -d ' \t\r\n')
      [[ -n "$night" ]] && NIGHTS_ARRAY+=("$night")
    done < "$NIGHTS_FILE"
  elif [[ -n "$NIGHTS_LIST" ]]; then
    # Parse comma-separated list
    IFS=',' read -ra NIGHTS_ARRAY <<< "$NIGHTS_LIST"
  else
    # Find all nights with processCcd outputs covering this tract+band
    echo "[discover] Finding nights with coverage for tract=${TRACT} band=${BAND}..."

    # Query for preliminary_visit_image datasets that overlap this tract (bash 3.x compatible)
    NIGHTS_ARRAY=()
    while IFS= read -r night; do
      NIGHTS_ARRAY+=("$night")
    done < <(
      butler query-datasets "$REPO" preliminary_visit_image \
        --collections "Nickel/runs/*/processCcd/*/run" \
        --where "instrument='Nickel' AND band='${BAND}'" \
        | awk 'NR>1 {print $0}' \
        | grep -oE '[0-9]{8}' \
        | sort -u
    )
  fi

  if [[ ${#NIGHTS_ARRAY[@]} -eq 0 ]]; then
    echo "ERROR: No nights found for template building"
    echo "  Specify --nights, --nights-file, or ensure processCcd outputs exist"
    exit 2
  fi

  echo "[nights] Found ${#NIGHTS_ARRAY[@]} nights: ${NIGHTS_ARRAY[*]}"

  # Build collection chain from nights
  # Look for collections matching: Nickel/runs/{NIGHT}/processCcd/*/run OR Nickel/runs/{NIGHT}/processCcd/*
  INPUT_COLLECTIONS_ARRAY=()
  for night in "${NIGHTS_ARRAY[@]}"; do
    # Find the parent collection for this night (newest if multiple)
    coll=$(butler query-collections "$REPO" \
      | awk '{print $1}' \
      | grep -E "^Nickel/runs/${night}/processCcd/" \
      | grep -v "/run$" \
      | tail -n1)

    if [[ -n "$coll" ]]; then
      INPUT_COLLECTIONS_ARRAY+=("$coll")
      echo "  + ${coll}"
    else
      echo "  ! WARNING: No processCcd collection found for night ${night}"
    fi
  done

  if [[ ${#INPUT_COLLECTIONS_ARRAY[@]} -eq 0 ]]; then
    echo "ERROR: No valid input collections found"
    exit 2
  fi

  # Join with commas
  INPUT_CHAIN=$(IFS=','; echo "${INPUT_COLLECTIONS_ARRAY[*]}")
fi

echo "[input chain] $INPUT_CHAIN"

########## BUILD DATA ID QUERY ##########
DATA_ID_QUERY="instrument='Nickel' AND skymap='${SKYMAP_NAME}' AND tract=${TRACT} AND band='${BAND}'"
if [[ -n "$PATCH" ]]; then
  DATA_ID_QUERY="${DATA_ID_QUERY} AND patch=${PATCH}"
fi

echo "[where] $DATA_ID_QUERY"

########## GENERATE QUANTUM GRAPH ##########
echo "[qgraph] Generating quantum graph -> $QG_FILE"

if ! pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#coadds-only" \
  -i "$INPUT_CHAIN","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN" \
  -o "$TEMPLATE_PARENT" \
  --output-run "$TEMPLATE_RUN" \
  --save-qgraph "$QG_FILE" \
  --qgraph-dot "$QG_DOT" \
  -d "$DATA_ID_QUERY"; then
  echo "[ERROR] Quantum graph generation failed"
  exit 2
fi

if [[ ! -s "$QG_FILE" ]]; then
  echo "[ERROR] Expected quantum graph not created: $QG_FILE"
  exit 2
fi

# Show quantum graph summary
echo ""
pipetask qgraph -b "$REPO" -g "$QG_FILE" --show tasks 2>/dev/null || true
echo ""

########## RUN COADD PIPELINE ##########
echo "[run] Building deep template coadds (jobs=${JOBS})..."
echo "      Log: $LOG_FILE"

if pipetask run \
    -b "$REPO" \
    -g "$QG_FILE" \
    --register-dataset-types \
    -j "$JOBS" \
    2>&1 | tee "$LOG_FILE"; then

  # Create/update collection chain
  butler collection-chain "$REPO" "$TEMPLATE_PARENT" "$TEMPLATE_RUN" --mode prepend >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$TEMPLATE_PARENT" "$TEMPLATE_RUN"

  echo ""
  echo "=== [30_coadds] SUCCESS ==="
  echo "Template collection: $TEMPLATE_RUN"
  echo "Template parent:     $TEMPLATE_PARENT"
  echo "Tract:               $TRACT"
  echo "Band:                $BAND"
  echo "Input nights:        ${#NIGHTS_ARRAY[@]}"
  echo ""

  # Query and show created datasets
  echo "[outputs] Deep coadds created:"
  butler query-datasets "$REPO" deep_coadd_predetection \
    --collections "$TEMPLATE_RUN" \
    --where "instrument='Nickel' AND tract=${TRACT} AND band='${BAND}'" \
    2>/dev/null | head -20 || true

  echo ""
  echo "[outputs] Template coadds created:"
  butler query-datasets "$REPO" template_coadd \
    --collections "$TEMPLATE_RUN" \
    --where "instrument='Nickel' AND tract=${TRACT} AND band='${BAND}'" \
    2>/dev/null | head -20 || true

  # Record template metadata (date range for DIA filtering)
  if [[ ${#NIGHTS_ARRAY[@]} -gt 0 ]]; then
    echo ""
    echo "[metadata] Recording template date range..."

    # Find min and max dates
    SORTED_NIGHTS=($(printf '%s\n' "${NIGHTS_ARRAY[@]}" | sort))
    START_DATE="${SORTED_NIGHTS[0]}"
    END_DATE="${SORTED_NIGHTS[-1]}"

    # Record metadata
    TEMPLATE_META_SCRIPT="$OBS_NICKEL/scripts/python/data/template_metadata.py"
    if [[ -f "$TEMPLATE_META_SCRIPT" ]]; then
      /opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$TEMPLATE_META_SCRIPT" record \
        --repo "$REPO" \
        --collection "$TEMPLATE_PARENT" \
        --start "$START_DATE" \
        --end "$END_DATE" \
        --tract "$TRACT" \
        --band "$BAND" \
        --description "Template from ${#NIGHTS_ARRAY[@]} nights (${START_DATE}-${END_DATE})" \
        2>&1 || echo "  (metadata recording failed, continuing)"
    fi
  fi

else
  echo ""
  echo "[ERROR] Template building failed; see log: $LOG_FILE"
  exit 2
fi
