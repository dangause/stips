#!/usr/bin/env bash
# 00_bootstrap_repo.sh
# Bootstrap a Butler repo and ingest GAIA/PS1 + MONSTER (AFW shards) refcats,
# and register a SkyMap run + chain.

# set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
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

# Use -r (path-based) setup so obs_nickel works even without eups registration
if [ -n "${OBS_NICKEL:-}" ] && [ -d "$OBS_NICKEL" ]; then
  setup -r "$OBS_NICKEL" obs_nickel 2>/dev/null || true
else
  setup obs_nickel || true
fi

OBS_NICKEL_DATA_DIR="${OBS_NICKEL%/*}/obs_nickel_data"
if [ -d "$OBS_NICKEL_DATA_DIR" ]; then
  setup -r "$OBS_NICKEL_DATA_DIR" obs_nickel_data 2>/dev/null || true
else
  setup obs_nickel_data || true
fi

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

########## REF CATS (MONSTER AFW only) ##########
log_section "Reference Catalogs Ingestion (MONSTER only)"
cd "$REFCAT_REPO"

MON_DIR="$REFCAT_REPO/data/refcats/the_monster_20250219_afw"
MON_DT="the_monster_20250219_local"
MON_RUN="refcats/${MON_DT}"
MON_MAP="$MON_DIR/filename_to_htm.ecsv"

if ! compgen -G "$MON_DIR/refcat_htm7_*.fits" > /dev/null; then
  log_error "No MONSTER refcat shards found under: $MON_DIR"
  log_error "Expected files like refcat_htm7_*.fits"
  print_log_summary
  exit 2
fi

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
    # Verify first data path actually exists (catches host/container path mismatch)
    FIRST_PATH=$(awk '!/^#/ && /^\// {print $1; exit}' "$MON_MAP")
    if [ -n "$FIRST_PATH" ] && [ ! -f "$FIRST_PATH" ]; then
      NEED_BUILD=1
      log_warn "ECSV paths stale (path not found: $FIRST_PATH); rebuilding"
    else
      log_info "Using existing ECSV map: $MON_MAP"
    fi
  fi
fi

INGEST_MAP="$MON_MAP"
if [[ $NEED_BUILD -eq 1 ]]; then
  # Try writing to the original location first; fall back to a writable
  # temp directory if the refcats are mounted read-only (e.g., Docker).
  if ! touch "$MON_MAP" 2>/dev/null; then
    INGEST_MAP="/tmp/nps_refcat_ecsv/filename_to_htm.ecsv"
    mkdir -p "$(dirname "$INGEST_MAP")"
    log_info "Refcats directory is read-only; writing ECSV to $INGEST_MAP"
  fi

  export MON_DIR
  export ECSV_OUT="$INGEST_MAP"
  python - <<'PY'
import os, re, glob
from astropy.table import Table
mon_dir = os.environ["MON_DIR"]
out = os.environ["ECSV_OUT"]
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

if [[ ! -s "$INGEST_MAP" ]]; then
  log_error "MONSTER filename_to_htm map missing after build: $INGEST_MAP"
  print_log_summary
  exit 2
fi

# Register dataset type (idempotent)
butler register-dataset-type "$REPO" "$MON_DT" SimpleCatalog htm7 || true

# Ingest AFW shards (direct = leave files in place)
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$MON_RUN"; then
  log_info "Ingesting MONSTER -> $MON_RUN"
  butler ingest-files -t direct "$REPO" "$MON_DT" "$MON_RUN" "$INGEST_MAP"
else
  log_info "MONSTER RUN already present: $MON_RUN"
fi

########## REF CATS chain ##########
log_section "Reference Catalog Chain Setup"
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$MON_RUN"; then
  butler collection-chain "$REPO" refcats "$MON_RUN" --mode redefine 2>/dev/null || \
  butler collection-chain "$REPO" refcats "$MON_RUN"
  log_info "refcats chain created: $MON_RUN"
else
  log_error "MONSTER collection missing; cannot create refcats chain"
  print_log_summary
  exit 2
fi

########## SKYMAP: register + alias to a stable chain ##########
log_section "SkyMap Registration"
SKYMAP_CFG="$OBS_NICKEL/configs/makeSkyMap.py"
log_info "Registering SkyMap (config: ${SKYMAP_CFG})"
SKYMAP_LOG="${LOG_DIR}/register_skymap_${TS}.log"
if ! butler register-skymap "$REPO" -C "$SKYMAP_CFG" > "$SKYMAP_LOG" 2>&1; then
  log_warn "register-skymap reported non-zero status; see ${SKYMAP_LOG}"
else
  log_info "register-skymap output captured in ${SKYMAP_LOG}"
fi

# In 11.0.0 weekly the default RUN is literally 'skymaps'.
log_info "Creating SkyMap chain: skymaps/nickelRings -> skymaps"
butler collection-chain "$REPO" skymaps/nickelRings skymaps --mode redefine \
  || butler collection-chain "$REPO" skymaps/nickelRings skymaps

# (Optional) sanity print
log_info "Verifying SkyMap datasets:"
butler query-datasets "$REPO" skyMap --collections skymaps/nickelRings | sed -n '1,50p'

log_section "Bootstrap Complete"
print_log_summary
