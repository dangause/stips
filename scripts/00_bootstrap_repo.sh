#!/usr/bin/env bash
# set -euo pipefail

set -a
source .env
set +a

########## ENVIRONMENT VARS ##########

INSTRUMENT="lsst.obs.nickel.Nickel"

TS="$(date -u +%Y%m%dT%H%M%SZ)"

echo "=== [bootstrap] start @ ${TS} ==="

########## LSST ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib; setup obs_nickel || true

########## REPO ##########
if [ ! -f "$REPO/butler.yaml" ]; then
  butler create "$REPO"
fi
butler register-instrument "$REPO" "$INSTRUMENT" || true


########## REF CATS (make a stable 'refcats' chain) ##########
cd "$REFCAT_REPO"

GAIA_DIR=$(ls -d data/gaia-refcat-* 2>/dev/null | sort -V | tail -n1 || true)
PS1_DIR=$(ls -d data/ps1-refcat-*  2>/dev/null | sort -V | tail -n1 || true)

if [[ -z "${GAIA_DIR}" || -z "${PS1_DIR}" ]]; then
  echo "[refcats] Missing converted outputs. Run your converter first (scripts/convert_refcats.py)."
  exit 2
fi

GAIA_DT="gaia_dr3";      GAIA_MAP="${GAIA_DIR}/filename_to_htm.ecsv"
PS1_DT="panstarrs1_dr2"; PS1_MAP="${PS1_DIR}/filename_to_htm.ecsv"
GAIA_RUN="refcats/${GAIA_DT}_${GAIA_DIR##*-}"
PS1_RUN="refcats/${PS1_DT}_${PS1_DIR##*-}"

[[ -s "$GAIA_MAP" && -s "$PS1_MAP" ]] || { echo "[refcats] filename_to_htm.ecsv missing"; exit 2; }

butler register-dataset-type "$REPO" "$GAIA_DT" SimpleCatalog htm7 || true
butler register-dataset-type "$REPO" "$PS1_DT" SimpleCatalog htm7 || true

if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$GAIA_RUN"; then
  butler ingest-files -t direct "$REPO" "$GAIA_DT" "$GAIA_RUN" "$GAIA_MAP"
fi
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$PS1_RUN"; then
  butler ingest-files -t direct "$REPO" "$PS1_DT" "$PS1_RUN" "$PS1_MAP"
fi

butler collection-chain "$REPO" refcats "$GAIA_RUN" "$PS1_RUN" --mode redefine

echo "=== [bootstrap] done ==="
