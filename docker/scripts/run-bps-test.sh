#!/usr/bin/env bash
# Smoke test for BPS execution in Docker Slurm environment.
#
# Runs inside the 'login' container. Verifies:
#   1. LSST stack is available
#   2. obs_nickel is setup
#   3. nickel CLI works
#   4. BPS submit to Slurm works (basic connectivity)
#
# Usage:
#   docker compose -f docker/docker-compose.slurm.yml exec nps /shared/scripts/run-bps-test.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed

set -euo pipefail

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
# 3. obs_nickel
# -------------------------------------------------------------------
echo "[3/5] obs_nickel"
if [[ -d /shared/obs_nickel ]]; then
    setup -r /shared/obs_nickel obs_nickel 2>/dev/null || true
fi
check "obs_nickel package exists" test -d /shared/obs_nickel
check "import lsst.obs.nickel" python -c "import lsst.obs.nickel"

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
# 5. nickel CLI (if data_tools installed)
# -------------------------------------------------------------------
echo "[5/5] nickel CLI"
if [[ -d /shared/data_tools ]]; then
    pip install -e /shared/data_tools 2>/dev/null || true
fi
check "nickel --help" nickel --help

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
