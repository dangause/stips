#!/usr/bin/env bash
# 20_science.sh — Nickel science processing (ProcessCcd + coadds + DIA)

# set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHT="${NIGHT:-}"
BAD_EXPOSURES=""; BAD_EXPOSURES_FILE=""
BAD_OBSIDS="";   BAD_OBSIDS_FILE=""
JOBS="${JOBS:-8}"   # default parallelism
OBJECT_FILTER=""    # optional object name filter
SKIP_COADDS=false   # run coadds by default

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)        NIGHT="${2:-}"; shift 2;;
    --bad)             BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)        BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    --bad-obs)         BAD_OBSIDS="${2:-}"; shift 2;;
    --bad-obs-file)    BAD_OBSIDS_FILE="${2:-}"; shift 2;;
    -j|--jobs)         JOBS="${2:-}"; shift 2;;
    --object)          OBJECT_FILTER="${2:-}"; shift 2;;
    --skip-coadds)     SKIP_COADDS=true; shift 1;;
    -h|--help)
      cat <<USAGE
Usage: $0 --night YYYYMMDD [options]

Options:
  --bad EXP_IDS             Comma- or space-separated exposure/visit IDs to exclude
  --bad-file FILE           File containing IDs to exclude (comments allowed)
  --bad-obs OBSNUMS         Comma- or space-separated OBSNUMs to exclude
  --bad-obs-file FILE       File containing OBSNUMs to exclude (comments allowed)
  -j, --jobs N              Number of parallel jobs for pipetask run (default: ${JOBS})
  --object NAME             Filter exposures by OBJECT header value (e.g., '2020wnt')
  --skip-coadds             Skip coadd generation (only run Stage 1 single-visit processing)
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done
[[ -n "$NIGHT" ]] || { echo "Provide --night YYYYMMDD"; exit 2; }

# Validate JOBS
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "Invalid -j/--jobs value: '$JOBS' (must be a positive integer)"; exit 2;
fi

########## ENVIRONMENT VARS ##########
INSTRUMENT="lsst.obs.nickel.Nickel"

# Pipeline & configs
PIPE="$OBS_NICKEL/pipelines/DRP.yaml"
# TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/custom_configs/config_robust.py"
TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"
APPLY_CT_CFG="$OBS_NICKEL/configs/apply_colorterms.py"

# Skymap (bootstrap chains this: skymaps/nickelRings -> skymaps)
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"

########## TIMESTAMPS & COLLECTIONS ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

# Stage-1 outputs
SCI_PARENT="Nickel/runs/${NIGHT}/processCcd/${RUN_TS}"
SCI_RUN="${SCI_PARENT}/run"

# Coadd + diff runs
COADD_PARENT="Nickel/runs/${NIGHT}/coadd/${RUN_TS}"
COADD_RUN="${COADD_PARENT}/run"
DIFF_PARENT="Nickel/runs/${NIGHT}/diff/${RUN_TS}"
DIFF_RUN="${DIFF_PARENT}/run"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"
LOGS_DIR="$OBS_NICKEL/logs"; mkdir -p "$LOGS_DIR"

QG_SCI="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.qg"
QG_SCI_DOT="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.dot"
QG_SCI_MMD="$QG_DIR/processCcd_${NIGHT}_${RUN_TS}.mmd"

QG_COADD="$QG_DIR/coadds_${NIGHT}_${RUN_TS}.qg"
QG_COADD_DOT="$QG_DIR/coadds_${NIGHT}_${RUN_TS}.dot"
QG_COADD_MMD="$QG_DIR/coadds_${NIGHT}_${RUN_TS}.mmd"

QG_DIFF="$QG_DIR/diff_${NIGHT}_${RUN_TS}.qg"
QG_DIFF_DOT="$QG_DIR/diff_${NIGHT}_${RUN_TS}.dot"
QG_DIFF_MMD="$QG_DIR/diff_${NIGHT}_${RUN_TS}.mmd"

echo "=== [science] night=${NIGHT} @ ${RUN_TS} (jobs=${JOBS}) ==="

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
# If the exact RAW_RUN isn't present yet, use latest for the night.
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }

# Optional quick check: confirm skyMap exists in the chain
if ! butler query-datasets "$REPO" skyMap --collections "$SKYMAPS_CHAIN" \
      --where "skymap='${SKYMAP_NAME}'" 2>/dev/null | grep -q skyMap; then
  echo "[ERROR] skyMap='${SKYMAP_NAME}' not found in '${SKYMAPS_CHAIN}'."
  echo "       Try re-running 00_bootstrap_repo.sh (skymap section)."
  exit 2
fi

echo "[inputs] RAW_RUN=$RAW_RUN  CALIB_CHAIN=$CALIB_CHAIN  REFCATS=$REFCATS_CHAIN  SKYMAPS=$SKYMAPS_CHAIN  SKYMAP_NAME=$SKYMAP_NAME"

########## EXCLUSIONS ##########
BAD_LIST="$BAD_EXPOSURES"
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then BAD_LIST="$BAD_LIST
$(cat "$BAD_EXPOSURES_FILE")"; fi
if [[ -n "$BAD_OBSIDS" ]]; then BAD_LIST="$BAD_LIST
$BAD_OBSIDS"; fi
if [[ -n "$BAD_OBSIDS_FILE" && -f "$BAD_OBSIDS_FILE" ]]; then BAD_LIST="$BAD_LIST
$(cat "$BAD_OBSIDS_FILE")"; fi

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

########## BUILD QGRAPH (stage1) ##########
CFG_ARG="calibrateImage:${TUNED_CFG_FILE}"
echo "[qgraph] processCcd -> $QG_SCI"

if ! pipetask qgraph \
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
  -d "instrument='Nickel' AND exposure.observation_type='science'${OBJECT_EXPR}${BAD_EXPR}"; then
  echo "[ERROR] pipetask qgraph (processCcd) failed."
  exit 2
fi

if [[ ! -s "$QG_SCI" ]]; then
  echo "[ERROR] Expected qgraph not created: $QG_SCI"
  exit 2
fi

# pipetask qgraph -b "$REPO" -g "$QG_SCI" --show tasks || true

echo "[run] processCcd ..."
if pipetask run \
    -b "$REPO" \
    -g "$QG_SCI" \
    --register-dataset-types \
    -j "$JOBS" \
    2>&1 | tee "$LOGS_DIR/processCcd_${RUN_TS}.log"; then
  butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN" --mode redefine >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN"
else
  echo "[ERROR] processCcd failed; see log: $LOGS_DIR/processCcd_${RUN_TS}.log"
  exit 2
fi

########## COADDS (from stage-1 prelim products) ##########
if [[ "$SKIP_COADDS" == "false" ]]; then
  echo "[qgraph] coadds -> $QG_COADD"

  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#coadds-only" \
    -i "$SCI_PARENT","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN" \
    -o "$COADD_PARENT" \
    --output-run "$COADD_RUN" \
    --save-qgraph "$QG_COADD" \
    --qgraph-dot "$QG_COADD_DOT" \
    --qgraph-mermaid "$QG_COADD_MMD" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}'"; then
    echo "[ERROR] pipetask qgraph (coadds) failed."
    exit 2
  fi

  if [[ ! -s "$QG_COADD" ]]; then
    echo "[ERROR] Expected qgraph not created: $QG_COADD"
    exit 2
  fi

  # pipetask qgraph -b "$REPO" -g "$QG_COADD" --show tasks || true

  echo "[run] coadds ..."
  if pipetask run \
      -b "$REPO" \
      -g "$QG_COADD" \
      --register-dataset-types \
      -j "$JOBS" \
      2>&1 | tee "$LOGS_DIR/coadds_${RUN_TS}.log"; then
    butler collection-chain "$REPO" "$COADD_PARENT" "$COADD_RUN" --mode redefine >/dev/null 2>&1 || \
    butler collection-chain "$REPO" "$COADD_PARENT" "$COADD_RUN"
  else
    echo "[ERROR] coadds failed; see log: $LOGS_DIR/coadds_${RUN_TS}.log"
    exit 2
  fi
else
  echo "[coadds] Skipped (--skip-coadds flag set)"
fi

# ########## DIFFERENCE IMAGING (visit-level)
# (unchanged; leave commented until you want it)

########## SUMMARY ##########
echo "=== [science] done ==="
echo "RAW_RUN     = $RAW_RUN"
echo "CALIB_CHAIN = $CALIB_CHAIN"
echo "REFCATS     = $REFCATS_CHAIN"
echo "SKYMAPS     = $SKYMAPS_CHAIN"
echo "SCI_PARENT  = $SCI_PARENT"
echo "SCI_RUN     = $SCI_RUN"
echo "COADD_PARENT= $COADD_PARENT"
echo "COADD_RUN   = $COADD_RUN"
echo "SKYMAP_NAME = $SKYMAP_NAME"
echo "JOBS        = $JOBS"
[[ -n "$OBJECT_FILTER" ]] && echo "OBJECT      = $OBJECT_FILTER"
