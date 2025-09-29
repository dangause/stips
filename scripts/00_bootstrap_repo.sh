#!/usr/bin/env bash
# 00_bootstrap_repo.sh
# Bootstrap a Butler repo and ingest GAIA/PS1 + MONSTER (AFW shards) refcats,
# and register a SkyMap run + chain.

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
setup lsst_distrib
setup obs_nickel || true

########## REPO ##########
if [ ! -f "$REPO/butler.yaml" ]; then
  butler create "$REPO"
fi
butler register-instrument "$REPO" "$INSTRUMENT" || true

########## REF CATS (GAIA/PS1; make a stable 'refcats' chain) ##########
cd "$REFCAT_REPO"

GAIA_DIR=$(ls -d data/gaia-refcat-* 2>/dev/null | sort -V | tail -n1 || true)
PS1_DIR=$(ls -d data/ps1-refcat-*  2>/dev/null | sort -V | tail -n1 || true)

if [[ -z "${GAIA_DIR}" || -z "${PS1_DIR}" ]]; then
  echo "[refcats] Missing converted outputs. Run your converter first (scripts/convert_refcats.py)."
  exit 2
fi

GAIA_DT="gaia_dr3"
PS1_DT="panstarrs1_dr2"

GAIA_MAP="${GAIA_DIR}/filename_to_htm.ecsv"
PS1_MAP="${PS1_DIR}/filename_to_htm.ecsv"

GAIA_RUN="refcats/${GAIA_DT}_${GAIA_DIR##*-}"
PS1_RUN="refcats/${PS1_DT}_${PS1_DIR##*-}"

[[ -s "$GAIA_MAP" && -s "$PS1_MAP" ]] || { echo "[refcats] filename_to_htm.ecsv missing"; exit 2; }

# Register dataset types (idempotent; positional: name storageClass dimensions...)
butler register-dataset-type "$REPO" "$GAIA_DT" SimpleCatalog htm7 || true
butler register-dataset-type "$REPO" "$PS1_DT" SimpleCatalog htm7 || true

# Ingest GAIA/PS1 via ingest-files (direct paths by default)
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$GAIA_RUN"; then
  echo "[gaia] ingest-files -> $GAIA_RUN"
  butler ingest-files -t direct "$REPO" "$GAIA_DT" "$GAIA_RUN" "$GAIA_MAP"
else
  echo "[gaia] RUN present: $GAIA_RUN"
fi

if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$PS1_RUN"; then
  echo "[ps1 ] ingest-files -> $PS1_RUN"
  butler ingest-files -t direct "$REPO" "$PS1_DT" "$PS1_RUN" "$PS1_MAP"
else
  echo "[ps1 ] RUN present: $PS1_RUN"
fi

########## MONSTER (AFW shards → ingest-files with a proper ECSV map) ##########
# Assume AFW SimpleCatalog FITS exist here (written from RSP):
#   $REFCAT_REPO/data/refcats/the_monster_20250219_afw/refcat_htm7_*.fits
MON_DIR="$REFCAT_REPO/data/refcats/the_monster_20250219_afw"
MON_DT="the_monster_20250219_local"
MON_RUN="refcats/${MON_DT}"
MON_MAP="$MON_DIR/filename_to_htm.ecsv"

if compgen -G "$MON_DIR/refcat_htm7_*.fits" > /dev/null; then
  echo "[monster] found AFW shard FITS in: $MON_DIR"

  # Build/repair a proper ECSV map (Astropy expects the ECSV header)
  NEED_BUILD=0
  if [[ ! -s "$MON_MAP" ]]; then
    NEED_BUILD=1
    echo "[monster] will build map: $MON_MAP"
  else
    # verify header is ECSV; if not, rebuild
    if ! head -n1 "$MON_MAP" | grep -q "^# %ECSV"; then
      NEED_BUILD=1
      echo "[monster] existing map is not ECSV; rebuilding: $MON_MAP"
    else
      echo "[monster] using existing ECSV map: $MON_MAP"
    fi
  fi

  if [[ $NEED_BUILD -eq 1 ]]; then
    export MON_DIR MON_MAP
    python - <<'PY'
import os, re, glob
from astropy.table import Table
mon_dir = os.environ["MON_DIR"]
out = os.environ["MON_MAP"]
rows = []
for fn in glob.glob(os.path.join(mon_dir, "refcat_htm7_*.fits")):
    m = re.search(r"refcat_htm7_(\d+)\.fits$", os.path.basename(fn))
    if m:
        rows.append((os.path.abspath(fn), int(m.group(1))))
rows.sort(key=lambda r: r[1])
tab = Table(rows=rows, names=["path","htm7"])
tab.write(out, format="ascii.ecsv", overwrite=True)
print(f"[monster] wrote ECSV: {out} rows={len(tab)}")
PY
  fi

  # Register dataset type (idempotent)
  butler register-dataset-type "$REPO" "$MON_DT" SimpleCatalog htm7 || true

  # Ingest AFW shards (direct = leave files in place)
  if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$MON_RUN"; then
    echo "[monster] ingest-files -> $MON_RUN"
    butler ingest-files -t direct "$REPO" "$MON_DT" "$MON_RUN" "$MON_MAP"
  else
    echo "[monster] RUN present: $MON_RUN"
  fi
else
  echo "[monster] no AFW shard FITS found under: $MON_DIR"
  echo "[monster] expected files like refcat_htm7_*.fits; skipping MONSTER ingest."
fi

########## REF CATS chain: prefer MONSTER, then GAIA, then PS1 ##########
CHAIN_CHILDREN=()
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$MON_RUN"; then
  CHAIN_CHILDREN+=("$MON_RUN")
fi
CHAIN_CHILDREN+=("$GAIA_RUN" "$PS1_RUN")

# Update/create the chain (try --mode redefine; fallback if not supported)
if [[ ${#CHAIN_CHILDREN[@]} -gt 0 ]]; then
  butler collection-chain "$REPO" refcats "${CHAIN_CHILDREN[@]}" --mode redefine 2>/dev/null || \
  butler collection-chain "$REPO" refcats "${CHAIN_CHILDREN[@]}"
  echo "[chain] refcats = ${CHAIN_CHILDREN[*]}"
else
  echo "[chain] nothing to chain"
fi

########## SKYMAP: register + make a *separate* chain alias ##########
SKYMAP_CFG="$OBS_NICKEL/configs/makeSkyMap.py"
SKYMAP_NAME="nickelRings-v1"
SKY_CHAIN="skymaps/nickelRings"

# Register (idempotent)
echo "[skymap] register-skymap -> ${SKYMAP_NAME} (cfg: ${SKYMAP_CFG})"
butler register-skymap "$REPO" -C "$SKYMAP_CFG"

# Find the run that holds this skyMap
SKY_RUN="$(butler query-datasets "$REPO" skyMap --where "skymap='${SKYMAP_NAME}'" \
          | awk 'NR>2{print $2}' | sort -u | tail -n1)"

if [[ -n "$SKY_RUN" ]]; then
  echo "[skymap] chaining: ${SKY_CHAIN} = ${SKY_RUN}"
  butler collection-chain "$REPO" "$SKY_CHAIN" "$SKY_RUN" --mode redefine 2>/dev/null \
    || butler collection-chain "$REPO" "$SKY_CHAIN" "$SKY_RUN"
else
  echo "[skymap] ERROR: could not locate a registered run for '${SKYMAP_NAME}'."
  echo "[skymap] Available skyMap datasets:"
  butler query-datasets "$REPO" skyMap | sed -n '1,200p'
fi

echo "=== [bootstrap] done ==="
