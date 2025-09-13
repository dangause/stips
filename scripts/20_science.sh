#!/usr/bin/env bash
# 20_science.sh — Nickel science processing (ProcessCcd + PostProc) with stable run names
# Usage:
#   20_science.sh --night YYYYMMDD [--bad EXP_IDS] [--bad-file FILE] [--bad-obs OBSNUMS] [--bad-obs-file FILE]
#
# Notes:
#  - Consumes calibrated chain and refcats built in 10_calibs.sh
#  - Uses DRP.yaml (your renamed ProcessCcd.yaml) and runs the "processCcd" subset
#  - Saves a deterministic child RUN via --output-run under a stable chained parent
#  - Builds a quantum graph, executes it, then optional post-processing + discrete skymap
#  - Quiet, robust, and idempotent where possible

# set -euo pipefail

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

########## USER PATHS ##########
REPO="/Users/dangause/Desktop/lick/lsst/data/nickel/repo"
OBS_NICKEL="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel"
STACK_DIR="/Users/dangause/Desktop/lick/lsst/lsst_stack"
INSTRUMENT="lsst.obs.nickel.Nickel"

# Pipeline files
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"                   # renamed ProcessCcd.yaml
TUNED_CFG="calibrateImage:configs/calibrateImage/tuned_configs/best_calib_t071.py"
POST_PIPE="$OBS_NICKEL/pipelines/PostProcessing.yaml"

########## TIMESTAMPS & COLLECTIONS ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"                 # must match ingest run from 10_calibs OR be present already
CALIB_CHAIN="Nickel/calib/current"                      # produced by 10_calibs.sh
REFCATS_CHAIN="refcats"                                 # your combined GAIA/PS1 chain

SCI_PARENT="Nickel/runs/${NIGHT}/processCcd/${RUN_TS}"  # stable chained parent for science step
SCI_RUN="${SCI_PARENT}/run"                             # deterministic child RUN

POST_PARENT="Nickel/run/postproc/visits/${RUN_TS}"
POST_RUN="${POST_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

echo "=== [science] night=${NIGHT} @ ${RUN_TS} ==="

########## ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

# Ensure instrument registered (idempotent)
butler register-instrument "$REPO" "$INSTRUMENT" || true

########## INPUT SANITY ##########
# RAW_RUN from 10_calibs.sh may be different if this script runs later; fall back to latest that matches the night.
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }
echo "[inputs] RAW_RUN=$RAW_RUN  CALIB_CHAIN=$CALIB_CHAIN  REFCATS=$REFCATS_CHAIN"

########## EXCLUSION FILTERS (bad exposures / obsnums) ##########
norm_csv_to_lines() { tr -cs '0-9,\n' '\n' | sed 's/^0\+//' | sed '/^$/d'; }
norm_file_to_lines() {
  local f="$1"; [[ -f "$f" ]] || return 0
  sed 's/#.*//' "$f" | tr -cs '0-9,\n' '\n' | sed 's/^0\+//' | sed '/^$/d'
}

BAD_EXP_CSV=""; BAD_OBS_CSV=""
if [[ -n "$BAD_EXPOSURES" ]]; then
  BAD_EXP_CSV="$(printf "%s" "$BAD_EXPOSURES" | norm_csv_to_lines | awk 'length($0)>=7' | sort -u | paste -sd, -)"
fi
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  ADD="$(norm_file_to_lines "$BAD_EXPOSURES_FILE" | awk 'length($0)>=7' | sort -u | paste -sd, -)"
  [[ -n "$ADD" ]] && BAD_EXP_CSV="${BAD_EXP_CSV:+$BAD_EXP_CSV,}$ADD"
fi
if [[ -n "$BAD_OBSIDS" ]]; then
  BAD_OBS_CSV="$(printf "%s" "$BAD_OBSIDS" | norm_csv_to_lines | awk 'length($0)>=1 && length($0)<=6' | sort -u | paste -sd, -)"
fi
if [[ -n "$BAD_OBSIDS_FILE" && -f "$BAD_OBSIDS_FILE" ]]; then
  ADD="$(norm_file_to_lines "$BAD_OBSIDS_FILE" | awk 'length($0)>=1 && length($0)<=6' | sort -u | paste -sd, -)"
  [[ -n "$ADD" ]] && BAD_OBS_CSV="${BAD_OBS_CSV:+$BAD_OBS_CSV,}$ADD"
fi

BAD_EXPR=""
if [[ -n "$BAD_EXP_CSV" ]]; then
  BAD_EXPR+=" AND NOT (exposure IN (${BAD_EXP_CSV}))"
fi
if [[ -n "$BAD_OBS_CSV" ]]; then
  local_quoted="$(printf "%s\n" "$BAD_OBS_CSV" | tr ',' '\n' | sed "s/.*/'&'/" | paste -sd, -)"
  BAD_EXPR+=" AND NOT (exposure.obs_id IN (${local_quoted}))"
fi
[[ -n "$BAD_EXP_CSV$BAD_OBS_CSV" ]] && echo "[exclude] exposures=(${BAD_EXP_CSV:-})  obsnums=(${BAD_OBS_CSV:-})"

########## BUILD & RUN: ProcessCcd ##########
QG_SCI="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.qgraph"

echo "[qgraph] processCcd -> $QG_SCI"
pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#processCcd" \
  -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN" \
  -o "$SCI_PARENT" \
  --output-run "$SCI_RUN" \
  --save-qgraph "$QG_SCI" \
  -C "$TUNED_CFG" \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}"

# (optional) peek at graph/tasks
pipetask qgraph -b "$REPO" -g "$QG_SCI" --show tasks --show counts || true

echo "[run] processCcd ..."
pipetask run \
  -b "$REPO" \
  -g "$QG_SCI" \
  --register-dataset-types \
  -j 8 \
  | tee "$LOGS_DIR/processCcd_${RUN_TS}.log"

# Ensure parent chain points to deterministic child RUN (some CLIs don't auto-create)
butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN" --mode redefine

########## OPTIONAL: Post-processing on visits ##########
QG_POST="$QG_DIR/postproc_visits_${NIGHT}_${RUN_TS}.qgraph"

echo "[qgraph] postproc (visits) -> $QG_POST"
pipetask qgraph \
  -b "$REPO" \
  -p "$POST_PIPE" \
  -i "$SCI_PARENT","$CALIB_CHAIN","$REFCATS_CHAIN" \
  -o "$POST_PARENT" \
  --output-run "$POST_RUN" \
  --save-qgraph "$QG_POST" \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}"

echo "[run] postproc (visits) ..."
pipetask run \
  -b "$REPO" \
  -g "$QG_POST" \
  --register-dataset-types \
  -j 8 \
  | tee "$LOGS_DIR/postproc_visits_${RUN_TS}.log"

# Ensure parent chain exists
butler collection-chain "$REPO" "$POST_PARENT" "$POST_RUN" --mode redefine

########## SKYMAP (discrete) — only if we produced initial_pvi ##########
cd "$OBS_NICKEL"
SKY_CFG="configs/makeSkyMap_discrete_auto.py"

if butler query-datasets "$REPO" initial_pvi --collections "$SCI_PARENT" | awk 'NR>1{print}' | grep -q .; then
  echo "[skymap] Building discrete skymap config from $SCI_PARENT (initial_pvi)"
  python scripts/build_discrete_skymap_config.py \
    --repo "$REPO" \
    --collections "$SCI_PARENT" \
    --dataset-type initial_pvi \
    --skymap-id nickel_discrete \
    --border-deg 0.05 \
    --out "$SKY_CFG"

  echo "[skymap] Registering"
  butler register-skymap "$REPO" -C "$SKY_CFG"
  butler query-datasets "$REPO" skyMap --where "skymap='nickel_discrete'" || true
else
  echo "[skymap] No 'initial_pvi' found in [$SCI_PARENT]; skipping skymap."
fi

########## SUMMARY ##########
echo "=== [science] done ==="
echo "RAW_RUN     = $RAW_RUN"
echo "CALIB_CHAIN = $CALIB_CHAIN"
echo "REFCATS     = $REFCATS_CHAIN"
echo "SCI_PARENT  = $SCI_PARENT"
echo "SCI_RUN     = $SCI_RUN"
echo "POST_PARENT = $POST_PARENT"
echo "POST_RUN    = $POST_RUN"
