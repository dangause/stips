#!/usr/bin/env bash
# 00_bootstrap_repo.sh
# Bootstrap a Butler repo and ingest GAIA/PS1 + MONSTER (AFW shards) refcats,
# and register a SkyMap run + chain.

# set -euo pipefail

set -a
source .env
set +a

# Source logging utilities
source "$(dirname "$0")/../utilities/logging.sh"

########## ENVIRONMENT VARS ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

# Setup logging (creates LOG_DIR and LOG_FILE)
setup_logging "bootstrap"

# Redirect all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Repository Bootstrap"
log_info "Timestamp: $TS"
log_info "Repository: $REPO"

########## LSST ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

########## REPO ##########
log_section "Butler Repository Setup"
if [ ! -f "$REPO/butler.yaml" ]; then
  log_info "Creating Butler repository: $REPO"
  butler create "$REPO"
else
  log_info "Butler repository exists: $REPO"
fi
log_info "Registering instrument: $INSTRUMENT"
butler register-instrument "$REPO" "$INSTRUMENT" || true

########## REF CATS (GAIA/PS1; make a stable 'refcats' chain) ##########
log_section "Reference Catalogs Ingestion"
cd "$REFCAT_REPO"

GAIA_DIR=$(ls -d data/gaia-refcat-* 2>/dev/null | sort -V | tail -n1 || true)
PS1_DIR=$(ls -d data/ps1-refcat-*  2>/dev/null | sort -V | tail -n1 || true)

if [[ -z "${GAIA_DIR}" || -z "${PS1_DIR}" ]]; then
  log_error "Missing converted outputs. Run your converter first (scripts/convert_refcats.py)."
  print_log_summary
  exit 2
fi

GAIA_DT="gaia_dr3"
PS1_DT="panstarrs1_dr2"

GAIA_MAP="${GAIA_DIR}/filename_to_htm.ecsv"
PS1_MAP="${PS1_DIR}/filename_to_htm.ecsv"

GAIA_RUN="refcats/${GAIA_DT}_${GAIA_DIR##*-}"
PS1_RUN="refcats/${PS1_DT}_${PS1_DIR##*-}"

if [[ ! -s "$GAIA_MAP" || ! -s "$PS1_MAP" ]]; then
  log_error "filename_to_htm.ecsv missing"
  print_log_summary
  exit 2
fi

# Register dataset types (idempotent; positional: name storageClass dimensions...)
butler register-dataset-type "$REPO" "$GAIA_DT" SimpleCatalog htm7 || true
butler register-dataset-type "$REPO" "$PS1_DT" SimpleCatalog htm7 || true

# Ingest GAIA/PS1 via ingest-files (direct paths by default)
log_info "Ingesting GAIA DR3 reference catalog"
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$GAIA_RUN"; then
  log_info "Ingesting GAIA -> $GAIA_RUN"
  butler ingest-files -t direct "$REPO" "$GAIA_DT" "$GAIA_RUN" "$GAIA_MAP"
else
  log_info "GAIA RUN already present: $GAIA_RUN"
fi

log_info "Ingesting PS1 DR2 reference catalog"
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$PS1_RUN"; then
  log_info "Ingesting PS1 -> $PS1_RUN"
  butler ingest-files -t direct "$REPO" "$PS1_DT" "$PS1_RUN" "$PS1_MAP"
else
  log_info "PS1 RUN already present: $PS1_RUN"
fi

########## MONSTER (AFW shards → ingest-files with a proper ECSV map) ##########
# Assume AFW SimpleCatalog FITS exist here (written from RSP):
#   $REFCAT_REPO/data/refcats/the_monster_20250219_afw/refcat_htm7_*.fits
log_section "MONSTER Reference Catalog"
MON_DIR="$REFCAT_REPO/data/refcats/the_monster_20250219_afw"
MON_DT="the_monster_20250219_local"
MON_RUN="refcats/${MON_DT}"
MON_MAP="$MON_DIR/filename_to_htm.ecsv"

if compgen -G "$MON_DIR/refcat_htm7_*.fits" > /dev/null; then
  log_info "Found AFW shard FITS in: $MON_DIR"

  # Build/repair a proper ECSV map (Astropy expects the ECSV header)
  NEED_BUILD=0
  if [[ ! -s "$MON_MAP" ]]; then
    NEED_BUILD=1
    log_info "Will build map: $MON_MAP"
  else
    # verify header is ECSV; if not, rebuild
    if ! head -n1 "$MON_MAP" | grep -q "^# %ECSV"; then
      NEED_BUILD=1
      log_warn "Existing map is not ECSV; rebuilding: $MON_MAP"
    else
      log_info "Using existing ECSV map: $MON_MAP"
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
    log_info "Ingesting MONSTER -> $MON_RUN"
    butler ingest-files -t direct "$REPO" "$MON_DT" "$MON_RUN" "$MON_MAP"
  else
    log_info "MONSTER RUN already present: $MON_RUN"
  fi
else
  log_warn "No AFW shard FITS found under: $MON_DIR"
  log_warn "Expected files like refcat_htm7_*.fits; skipping MONSTER ingest"
fi

########## REF CATS chain: prefer MONSTER, then GAIA, then PS1 ##########
log_section "Reference Catalog Chain Setup"
CHAIN_CHILDREN=()
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$MON_RUN"; then
  CHAIN_CHILDREN+=("$MON_RUN")
fi
CHAIN_CHILDREN+=("$GAIA_RUN" "$PS1_RUN")

# Update/create the chain (try --mode redefine; fallback if not supported)
if [[ ${#CHAIN_CHILDREN[@]} -gt 0 ]]; then
  butler collection-chain "$REPO" refcats "${CHAIN_CHILDREN[@]}" --mode redefine 2>/dev/null || \
  butler collection-chain "$REPO" refcats "${CHAIN_CHILDREN[@]}"
  log_info "refcats chain created: ${CHAIN_CHILDREN[*]}"
else
  log_warn "No collections to chain"
fi

########## SKYMAP: register + alias to a stable chain ##########
log_section "SkyMap Registration"
SKYMAP_CFG="$OBS_NICKEL/configs/makeSkyMap.py"
log_info "Registering SkyMap (config: ${SKYMAP_CFG})"
butler register-skymap "$REPO" -C "$SKYMAP_CFG" || true

# In 11.0.0 weekly the default RUN is literally 'skymaps'.
log_info "Creating SkyMap chain: skymaps/nickelRings -> skymaps"
butler collection-chain "$REPO" skymaps/nickelRings skymaps --mode redefine \
  || butler collection-chain "$REPO" skymaps/nickelRings skymaps

# (Optional) sanity print
log_info "Verifying SkyMap datasets:"
butler query-datasets "$REPO" skyMap --collections skymaps/nickelRings | sed -n '1,50p'

log_section "Bootstrap Complete"
print_log_summary
