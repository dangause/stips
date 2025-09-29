#!/usr/bin/env bash
# 20_science.sh — Nickel science processing (ProcessCcd + visit-level analysis subset)

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

# Pipeline & configs
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
APPLY_CT_CFG="$OBS_NICKEL/configs/apply_colorterms.py"

########## TIMESTAMPS & COLLECTIONS ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"
SKYMAPS_CHAIN="skymaps/nickelRings"   # from 00_bootstrap_repo.sh

SCI_PARENT="Nickel/runs/${NIGHT}/processCcd/${RUN_TS}"
SCI_RUN="${SCI_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

QG_SCI="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.qgraph"
QG_SCI_DOT="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.dot"
QG_SCI_MMD="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.mmd"

echo "=== [science] night=${NIGHT} @ ${RUN_TS} ==="

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: pipeline not found: $PIPE"; exit 2; }
[[ -s "$TUNED_CFG_FILE" ]] || { echo "ERROR: tuned config not found: $TUNED_CFG_FILE"; exit 2; }
[[ -s "$APPLY_CT_CFG" ]] || { echo "ERROR: color-terms config not found: $APPLY_CT_CFG"; exit 2; }

########## INPUT SANITY ##########
# If the exact RAW_RUN isn’t present yet, use latest for the night.
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }
echo "[inputs] RAW_RUN=$RAW_RUN  CALIB_CHAIN=$CALIB_CHAIN  REFCATS=$REFCATS_CHAIN  SKYMAPS=$SKYMAPS_CHAIN"

########## EXCLUSIONS ##########
BAD_LIST="$BAD_EXPOSURES"
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  BAD_LIST="$BAD_LIST
$(cat "$BAD_EXPOSURES_FILE")"
fi
if [[ -n "$BAD_OBSIDS" ]]; then
  BAD_LIST="$BAD_LIST
$BAD_OBSIDS"
fi
if [[ -n "$BAD_OBSIDS_FILE" && -f "$BAD_OBSIDS_FILE" ]]; then
  BAD_LIST="$BAD_LIST
$(cat "$BAD_OBSIDS_FILE")"
fi

BAD_EXP_CSV="$(
  printf "%s\n" "$BAD_LIST" \
  | sed -E 's/#.*//; s/[^0-9]+/\n/g' \
  | awk 'NF' | sort -n -u | paste -sd, -
)"
BAD_EXPR=""
if [[ -n "$BAD_EXP_CSV" ]]; then
  BAD_EXPR=" AND NOT (exposure IN (${BAD_EXP_CSV}) OR visit IN (${BAD_EXP_CSV}))"
  echo "[exclude] exposure/visit: ${BAD_EXP_CSV}"
else
  echo "[exclude] none"
fi

########## BUILD QGRAPH (stage1-single-visit subset) ##########
CFG_ARG="calibrateImage:${TUNED_CFG_FILE}"
echo "[qgraph] processCcd -> $QG_SCI"

pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#stage1-single-visit" \
  -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN" \
  -o "$SCI_PARENT" \
  --output-run "$SCI_RUN" \
  --save-qgraph "$QG_SCI" \
  --config-file "$CFG_ARG" \
  --config-file "calibrateImage:${APPLY_CT_CFG}" \
  --qgraph-dot "$QG_SCI_DOT" \
  --qgraph-mermaid "$QG_SCI_MMD" \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}"

# Quick peek at tasks in the graph
pipetask qgraph -b "$REPO" -g "$QG_SCI" --show tasks || true

########## RUN ##########
echo "[run] processCcd ..."
pipetask run \
  -b "$REPO" \
  -g "$QG_SCI" \
  --register-dataset-types \
  -j 8 \
  2>&1 | tee "$LOGS_DIR/processCcd_${RUN_TS}.log"

# Ensure parent chain points at the run
butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN" --mode redefine >/dev/null 2>&1 || \
butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN"

########## SUMMARY ##########
echo "=== [science] done ==="
echo "RAW_RUN     = $RAW_RUN"
echo "CALIB_CHAIN = $CALIB_CHAIN"
echo "REFCATS     = $REFCATS_CHAIN"
echo "SKYMAPS     = $SKYMAPS_CHAIN"
echo "SCI_PARENT  = $SCI_PARENT"
echo "SCI_RUN     = $SCI_RUN"
