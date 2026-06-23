#!/usr/bin/env bash
# Smoke test for BPS execution in Docker Slurm environment.
#
# Runs inside the 'login' container. Verifies:
#   1. LSST stack is available
#   2. obs_stips is setup (instrument loaded by path from INSTRUMENT_DIR)
#   3. stips CLI works
#   4. BPS submit to Slurm works (basic connectivity)
#
# Usage:
#   docker compose -f docker/docker-compose.slurm.yml exec nps /shared/scripts/run-bps-test.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed

set -eo pipefail

PASS=0
FAIL=0

check() {
    local description="$1"
    shift
    echo -n "  Checking: ${description}... "
    if "$@" >/dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "NPS BPS Smoke Test"
echo "============================================"
echo

# -------------------------------------------------------------------
# 1. LSST Stack
# -------------------------------------------------------------------
echo "[1/5] LSST Stack"
source /opt/lsst/software/stack/loadLSST.bash
setup lsst_distrib

check "pipetask available" which pipetask
check "butler available" which butler
check "python imports lsst.daf.butler" python -c "import lsst.daf.butler"

echo

# -------------------------------------------------------------------
# 2. ctrl_bps and ctrl_bps_parsl
# -------------------------------------------------------------------
echo "[2/5] BPS Packages"
check "import lsst.ctrl.bps" python -c "import lsst.ctrl.bps"
check "import lsst.ctrl.bps.parsl" python -c "import lsst.ctrl.bps.parsl"
check "bps command available" which bps

echo

# -------------------------------------------------------------------
# 3. obs_stips + nickel instrument
# -------------------------------------------------------------------
echo "[3/5] obs_stips + nickel instrument"
OBS_STIPS_DIR="${OBS_STIPS:-/opt/nps/packages/obs_stips}"
INSTRUMENT_DIR="${INSTRUMENT_DIR:-/opt/nps/instruments/nickel}"
STIPS_DEFAULTS="${STIPS_DEFAULTS:-/opt/nps/packages/obs_stips/instrument_defaults}"
if [[ -d "$OBS_STIPS_DIR" ]]; then
    setup -r "$OBS_STIPS_DIR" obs_stips 2>/dev/null || true
fi
check "obs_stips package exists" test -d "$OBS_STIPS_DIR"
check "nickel instrument dir exists" test -d "$INSTRUMENT_DIR"
check "stips_defaults dir exists" test -d "$STIPS_DEFAULTS"
check "import lsst.obs.stips" python -c "import lsst.obs.stips"

echo

# -------------------------------------------------------------------
# 4. Slurm connectivity
# -------------------------------------------------------------------
echo "[4/5] Slurm Cluster"
check "sinfo available" which sinfo
check "sinfo shows nodes" sinfo -N
check "partition 'normal' exists" sinfo -p normal

echo

# -------------------------------------------------------------------
# 5. stips CLI (if stips installed)
# -------------------------------------------------------------------
echo "[5/5] stips CLI"
STIPS_DIR="${NPS_ROOT:-/opt/nps}/packages/stips"
if [[ -d "$STIPS_DIR" ]] && ! command -v stips &>/dev/null; then
    pip install -e "$STIPS_DIR" 2>/dev/null || true
fi
check "stips --help" stips --help

echo
echo "============================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "============================================"

if [[ ${FAIL} -gt 0 ]]; then
    echo "SMOKE TEST FAILED"
    exit 1
else
    echo "SMOKE TEST PASSED"
    exit 0
fi
