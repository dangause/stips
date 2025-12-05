#!/usr/bin/env bash
# 10_calibs.sh — Nickel nightly calibrations (bias/flat/defects) with stable run names
# Usage: 10_calibs.sh --night YYYYMMDD

# set -euo pipefail

set -a
source .env
set +a

########## CLI ##########
NIGHT="${NIGHT:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night) NIGHT="${2:-}"; shift 2;;
    -h|--help)  echo "Usage: $0 --night YYYYMMDD"; exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done
[[ -n "$NIGHT" ]] || { echo "Provide --night YYYYMMDD"; exit 2; }

########## ENVIRONMENT VARS ##########
RAWDIR=${RAW_PARENT_DIR}/${NIGHT}/raw
INSTRUMENT="lsst.obs.nickel.Nickel"

# cpPipe pipeline location (must exist; contains pipelines/_ingredients/*.yaml)
: "${CP_PIPE_DIR:?Set CP_PIPE_DIR to the cpPipe pipelines root (contains pipelines/_ingredients/*.yaml)}"

########## TIMESTAMPS & COLLECTION NAMES (single run timestamp) ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"

# Chained collections for CP outputs (stable parents)
CP_RUN_BIAS="Nickel/cp/${NIGHT}/bias/${RUN_TS}"
CP_RUN_FLAT="Nickel/cp/${NIGHT}/flat/${RUN_TS}"
# Deterministic child RUN names under each chained collection
CP_RUN_BIAS_RUN="${CP_RUN_BIAS}/run"
CP_RUN_FLAT_RUN="${CP_RUN_FLAT}/run"

DEFECTS_RUN="Nickel/calib/defects/${RUN_TS}"

CURATED_RUN="Nickel/calib/curated/${RUN_TS}"
CURATED_CHAIN="Nickel/calib/curated"     # stable alias

CALIB_OUT="Nickel/calib/${NIGHT}"         # nightly certification target
CALIB_CHAIN="Nickel/calib/current"        # unified chain for science

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"

echo "=== [calibs] night=${NIGHT} @ ${RUN_TS} ==="

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

########## INGEST RAWS ##########
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

echo "[ingest] raws -> $RAW_RUN"
# If re-running, ingest-raws will skip already-present files when transfer=copy.
butler ingest-raws "$REPO" "$RAWDIR" --transfer copy --output-run "$RAW_RUN"

# Define visits for Nickel (idempotent)
butler define-visits "$REPO" Nickel

########## CURATED CALIBS ##########
echo "[curated] write -> $CURATED_RUN (scanning $RAW_RUN)"
butler write-curated-calibrations "$REPO" Nickel "$RAW_RUN" --collection "$CURATED_RUN"
butler collection-chain "$REPO" "$CURATED_CHAIN" "$CURATED_RUN" --mode redefine

########## cpBias (qgraph -> run) ##########
QG_BIAS="$QG_DIR/cp_bias_${NIGHT}_${RUN_TS}.qg"
echo "[cpBias] inputs=[$CURATED_CHAIN,$RAW_RUN]  out=$CP_RUN_BIAS  child=$CP_RUN_BIAS_RUN"
pipetask qgraph \
  -b "$REPO" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml" \
  -i "$CURATED_CHAIN","$RAW_RUN" \
  -o "$CP_RUN_BIAS" \
  --output-run "$CP_RUN_BIAS_RUN" \
  --save-qgraph "$QG_BIAS" \
  -d "instrument='Nickel' AND exposure.observation_type='bias'"

echo "[run] cpBias ..."
if pipetask run \
    -b "$REPO" \
    -g "$QG_BIAS" \
    --register-dataset-types; then
  :
else
  echo "[ERROR] cpBias failed"; exit 2
fi

# Ensure child RUN exists, then (re)define the parent chain
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CP_RUN_BIAS_RUN"; then
  echo "ERROR: bias child RUN missing: $CP_RUN_BIAS_RUN"; exit 2
fi
butler collection-chain "$REPO" "$CP_RUN_BIAS" "$CP_RUN_BIAS_RUN" --mode redefine

# Sanity
butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CP_RUN_BIAS" \
  || { echo "ERROR: bias chained collection still missing: $CP_RUN_BIAS"; exit 2; }

########## CERTIFY BIAS (before cpFlat so time-valid matching works) ##########
BEGIN_ISO="$(python - "$NIGHT" <<'PY'
from datetime import datetime, timezone
import sys
dt = datetime.strptime(sys.argv[1], "%Y%m%d").replace(tzinfo=timezone.utc)
print(dt.strftime("%Y-%m-%dT%H:%M:%S"))
PY
)"
END_ISO="$(python - "$NIGHT" <<'PY'
from datetime import datetime, timezone, timedelta
import sys
dt = datetime.strptime(sys.argv[1], "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(days=2)
print(dt.strftime("%Y-%m-%dT%H:%M:%S"))
PY
)"

echo "[certify] bias -> $CALIB_OUT  ($BEGIN_ISO .. $END_ISO)"
butler certify-calibrations "$REPO" "$CP_RUN_BIAS" "$CALIB_OUT" bias \
  --begin-date "$BEGIN_ISO" --end-date "$END_ISO"

########## cpFlat (qgraph -> run) ##########
QG_FLAT="$QG_DIR/cp_flat_${NIGHT}_${RUN_TS}.qg"
echo "[cpFlat] inputs=[$CURATED_CHAIN,$RAW_RUN,$CALIB_OUT,$CP_RUN_BIAS_RUN]  out=$CP_RUN_FLAT  child=$CP_RUN_FLAT_RUN"
pipetask qgraph \
  -b "$REPO" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml" \
  -i "$CURATED_CHAIN","$RAW_RUN","$CALIB_OUT","$CP_RUN_BIAS_RUN" \
  -o "$CP_RUN_FLAT" \
  --output-run "$CP_RUN_FLAT_RUN" \
  --save-qgraph "$QG_FLAT" \
  -d "instrument='Nickel' AND exposure.observation_type='flat'" \
  -c cpFlatIsr:doDark=False \
  -c cpFlatIsr:doOverscan=True

echo "[run] cpFlat ..."
if pipetask run \
    -b "$REPO" \
    -g "$QG_FLAT" \
    --register-dataset-types; then
  :
else
  echo "[ERROR] cpFlat failed"; exit 2
fi

# Ensure child RUN exists, then (re)define the parent chain
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CP_RUN_FLAT_RUN"; then
  echo "ERROR: flat child RUN missing: $CP_RUN_FLAT_RUN"; exit 2
fi
butler collection-chain "$REPO" "$CP_RUN_FLAT" "$CP_RUN_FLAT_RUN" --mode redefine

# Sanity
butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CP_RUN_FLAT" \
  || { echo "ERROR: flat chained collection still missing: $CP_RUN_FLAT"; exit 2; }

########## DEFECTS (from flats; use the child RUN for deterministic reads) ##########
echo "[defects] from $CP_RUN_FLAT_RUN -> $DEFECTS_RUN"
python "$OBS_NICKEL"/scripts/defects/make_defects_from_flats.py \
  --repo "$REPO" \
  --collection "$CP_RUN_FLAT_RUN" \
  --invert-manual-y \
  --manual-box 255 0 2 1024 \
  --manual-box 783 0 2 977 \
  --manual-box 1000 0 25 1024 \
  --manual-box 45 120 6 9 \
  --manual-box 980 200 12 8 \
  --register \
  --ingest \
  --defects-run "$DEFECTS_RUN" \
  --plot

# Point the current-defects chain if the defects run exists
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$DEFECTS_RUN"; then
  butler collection-chain "$REPO" Nickel/calib/defects/current "$DEFECTS_RUN" --mode redefine
else
  echo "[defects] WARNING: defects run not found ($DEFECTS_RUN); skipping chain update."
fi

########## CERTIFY NIGHTLY FLATS (bias already certified) ##########
HAS_FLAT=0
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CALIB_OUT"; then
  echo "[check] Nightly calib collection exists: $CALIB_OUT"
  HAS_FLAT=$({ butler query-datasets "$REPO" flat --collections "$CALIB_OUT" \
                --where "instrument='Nickel'" 2>/dev/null || true; } \
             | awk 'NR>1{print}' | wc -l | tr -d ' ')
else
  echo "[check] Nightly calib collection not found yet: $CALIB_OUT (fresh repo)."
fi

if [ "$HAS_FLAT" -eq 0 ]; then
  echo "[certify] flat -> $CALIB_OUT  ($BEGIN_ISO .. $END_ISO)"
  butler certify-calibrations "$REPO" "$CP_RUN_FLAT" "$CALIB_OUT" flat \
    --begin-date "$BEGIN_ISO" --end-date "$END_ISO"
else
  echo "[certify] flats already present in $CALIB_OUT — skipping."
fi

########## UNIFIED CALIB CHAIN FOR SCIENCE ##########
echo "[calib-chain] $CALIB_CHAIN = [$CALIB_OUT, Nickel/calib/defects/current, $CURATED_CHAIN]"
butler collection-chain "$REPO" "$CALIB_CHAIN" \
  "$CALIB_OUT" Nickel/calib/defects/current "$CURATED_CHAIN" \
  --mode redefine

########## SUMMARY ##########
echo "=== [calibs] done ==="
echo "RAW_RUN         = $RAW_RUN"
echo "CURATED_RUN     = $CURATED_RUN"
echo "CP_RUN_BIAS     = $CP_RUN_BIAS"
echo "CP_RUN_BIAS_RUN = $CP_RUN_BIAS_RUN"
echo "CP_RUN_FLAT     = $CP_RUN_FLAT"
echo "CP_RUN_FLAT_RUN = $CP_RUN_FLAT_RUN"
echo "DEFECTS_RUN     = $DEFECTS_RUN"
echo "CALIB_OUT       = $CALIB_OUT"
echo "CALIB_CHAIN     = $CALIB_CHAIN"
