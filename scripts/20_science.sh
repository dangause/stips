#!/usr/bin/env bash
# 20_science.sh — Nickel science processing (ProcessCcd + PostProc) with stable run names

# set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHT="${NIGHT:-}"
BAD_EXPOSURES=""; BAD_EXPOSURES_FILE=""
BAD_OBSIDS="";   BAD_OBSIDS_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)        NIGHT="${2:-}"; shift 2;;
    --bad)             BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)        BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    --bad-obs)         BAD_OBSIDS="${2:-}"; shift 2;;
    --bad-obs-file)    BAD_OBSIDS_FILE="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --night YYYYMMDD [--bad EXP_IDS] [--bad-file FILE] [--bad-obs OBSNUMS] [--bad-obs-file FILE]
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done
[[ -n "$NIGHT" ]] || { echo "Provide --night YYYYMMDD"; exit 2; }


########## ENVIRONMENT VARS ##########
INSTRUMENT="lsst.obs.nickel.Nickel"

# Pipeline files (absolute)
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
POST_PIPE="$OBS_NICKEL/pipelines/PostProcessing.yaml"

########## TIMESTAMPS & COLLECTIONS ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

SCI_PARENT="Nickel/runs/${NIGHT}/processCcd/${RUN_TS}"
SCI_RUN="${SCI_PARENT}/run"

POST_PARENT="Nickel/run/postproc/visits/${RUN_TS}"
POST_RUN="${POST_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

# Paths (next to your existing QG_* paths)
QG_SCI_DOT="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.dot"
QG_SCI_MMD="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.mmd"
QG_SCI_SVG="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.svg"

QG_POST_DOT="$QG_DIR/postproc_visits_${NIGHT}_${RUN_TS}.dot"
QG_POST_MMD="$QG_DIR/postproc_visits_${NIGHT}_${RUN_TS}.mmd"
QG_POST_SVG="$QG_DIR/postproc_visits_${NIGHT}_${RUN_TS}.svg"


echo "=== [science] night=${NIGHT} @ ${RUN_TS} ==="

########## ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" || true

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: pipeline not found: $PIPE"; exit 2; }
[[ -s "$TUNED_CFG_FILE" ]] || { echo "ERROR: tuned config not found: $TUNED_CFG_FILE"; exit 2; }
[[ -s "$POST_PIPE" ]] || { echo "ERROR: post pipeline not found: $POST_PIPE"; exit 2; }

########## INPUT SANITY ##########
# Use the latest RAW run for that night if the fresh timestamped one is not present.
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }
echo "[inputs] RAW_RUN=$RAW_RUN  CALIB_CHAIN=$CALIB_CHAIN  REFCATS=$REFCATS_CHAIN"

########## EXCLUSION FILTERS (simple) ##########
# Gather bad IDs from --bad and/or --bad-file.
BAD_LIST="$BAD_EXPOSURES"
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  BAD_LIST="$BAD_LIST
$(cat "$BAD_EXPOSURES_FILE")"
fi

# Normalize: strip comments, turn anything non-digit into newlines, uniq+sort, -> CSV.
BAD_EXP_CSV="$(
  printf "%s\n" "$BAD_LIST" \
  | sed -E 's/#.*//; s/[^0-9]+/\n/g' \
  | awk 'NF' \
  | sort -n -u \
  | paste -sd, -
)"

BAD_EXPR=""
if [[ -n "$BAD_EXP_CSV" ]]; then
  # Exclude by both exposure and visit (covers tasks that key on either)
  BAD_EXPR=" AND NOT (exposure IN (${BAD_EXP_CSV}) OR visit IN (${BAD_EXP_CSV}))"
  echo "[exclude] exposure/visit: ${BAD_EXP_CSV}"
else
  echo "[exclude] none"
fi


########## BUILD & RUN: ProcessCcd ##########
QG_SCI="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.qgraph"
CFG_ARG="calibrateImage:$TUNED_CFG_FILE"   # build safely to avoid empty -C

echo "[qgraph] processCcd -> $QG_SCI"
pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#stage1-single-visit" \
  -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN" \
  -o "$SCI_PARENT" \
  --output-run "$SCI_RUN" \
  --save-qgraph "$QG_SCI" \
  --config-file "$CFG_ARG" \
  --config-file "calibrateImage:$OBS_NICKEL/configs/apply_colorterms.py" \
  --qgraph-dot "$QG_SCI_DOT" \
  --qgraph-mermaid "$QG_SCI_MMD" \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}"

# (optional) peek at graph/tasks (no 'counts' — not a valid show item)
pipetask qgraph -b "$REPO" -g "$QG_SCI" --show tasks || true

echo "[run] processCcd ..."
pipetask run \
  -b "$REPO" \
  -g "$QG_SCI" \
  --register-dataset-types \
  -j 8 \
  2>&1 | tee "$LOGS_DIR/processCcd_${RUN_TS}.log"

# Ensure parent chain points to child RUN
butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN" --mode redefine

# ########## OPTIONAL: Post-processing on visits ##########
# QG_POST="$QG_DIR/postproc_visits_${NIGHT}_${RUN_TS}.qgraph"

# echo "[qgraph] postproc (visits) -> $QG_POST"
# pipetask qgraph \
#   -b "$REPO" \
#   -p "$POST_PIPE" \
#   -i "$SCI_PARENT","$CALIB_CHAIN","$REFCATS_CHAIN" \
#   -o "$POST_PARENT" \
#   --output-run "$POST_RUN" \
#   --save-qgraph "$QG_POST" \
#   --qgraph-dot "$QG_POST_DOT" \
#   --qgraph-mermaid "$QG_POST_MMD" \
#   -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}"

# echo "[run] postproc (visits) ..."
# pipetask run \
#   -b "$REPO" \
#   -g "$QG_POST" \
#   --register-dataset-types \
#   -j 8 \
#   2>&1 | tee "$LOGS_DIR/postproc_visits_${RUN_TS}.log"

# butler collection-chain "$REPO" "$POST_PARENT" "$POST_RUN" --mode redefine

# ########## SKYMAP (discrete) — only if we produced initial_pvi ##########
# cd "$OBS_NICKEL"
# SKY_CFG="configs/makeSkyMap_discrete_auto.py"

# if butler query-datasets "$REPO" initial_pvi --collections "$SCI_PARENT" | awk 'NR>1{print}' | grep -q .; then
#   echo "[skymap] Building discrete skymap config from $SCI_PARENT (initial_pvi)"
#   python scripts/build_discrete_skymap_config.py \
#     --repo "$REPO" \
#     --collections "$SCI_PARENT" \
#     --dataset-type initial_pvi \
#     --skymap-id nickel_discrete \
#     --border-deg 0.05 \
#     --out "$SKY_CFG"

#   echo "[skymap] Registering"
#   butler register-skymap "$REPO" -C "$SKY_CFG"
#   butler query-datasets "$REPO" skyMap --where "skymap='nickel_discrete'" || true
# else
#   echo "[skymap] No 'initial_pvi' found in [$SCI_PARENT]; skipping skymap."
# fi

########## SUMMARY ##########
echo "=== [science] done ==="
echo "RAW_RUN     = $RAW_RUN"
echo "CALIB_CHAIN = $CALIB_CHAIN"
echo "REFCATS     = $REFCATS_CHAIN"
echo "SCI_PARENT  = $SCI_PARENT"
echo "SCI_RUN     = $SCI_RUN"
# echo "POST_PARENT = $POST_PARENT"
# echo "POST_RUN    = $POST_RUN"
