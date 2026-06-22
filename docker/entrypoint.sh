#!/bin/bash
# Nickel Processing Suite Container Entrypoint
#
# This script:
# 1. Sources the LSST stack
# 2. Sets up obs_stips and obs_nickel_data (instrument is declarative, by path)
# 3. Loads environment from mounted config if present
# 4. Executes the provided command

set -e

# =============================================================================
# LSST Stack Activation
# =============================================================================

echo "[NPS] Activating LSST Science Pipelines..."
source "${STACK_DIR}/loadLSST.bash"
setup lsst_distrib

# =============================================================================
# NPS Package Setup
# =============================================================================

# Setup obs_stips (generic LSST glue). The nickel instrument is declarative
# and loaded by path from INSTRUMENT_DIR — no EUPS setup required.
OBS_STIPS="${OBS_STIPS:-${NPS_ROOT}/packages/obs_stips}"
if [[ -d "${OBS_STIPS}" ]]; then
    echo "[NPS] Setting up obs_stips from ${OBS_STIPS}"
    setup -r "${OBS_STIPS}" obs_stips 2>/dev/null || true
fi

# Setup obs_nickel_data
if [[ -d "${OBS_NICKEL_DATA}" ]]; then
    echo "[NPS] Setting up obs_nickel_data from ${OBS_NICKEL_DATA}"
    setup -r "${OBS_NICKEL_DATA}" obs_nickel_data 2>/dev/null || true
fi

# Add stips to PYTHONPATH
STIPS_SRC="${NPS_ROOT}/packages/stips/src"
if [[ -d "${STIPS_SRC}" ]]; then
    export PYTHONPATH="${STIPS_SRC}:${PYTHONPATH:-}"
fi

# Ensure conda bin is in PATH (for pip-installed scripts like 'stips')
if [[ -n "${CONDA_PREFIX}" ]]; then
    export PATH="${CONDA_PREFIX}/bin:${PATH}"
fi

# =============================================================================
# Configuration Loading
# =============================================================================

# Load .env from mounted config directory if present
if [[ -f "/config/.env" ]]; then
    echo "[NPS] Loading configuration from /config/.env"
    set -a
    source /config/.env
    set +a
fi

# Load profile-specific .env if NPS_PROFILE is set
if [[ -n "${NPS_PROFILE}" && -f "/config/.env.${NPS_PROFILE}" ]]; then
    echo "[NPS] Loading profile configuration from /config/.env.${NPS_PROFILE}"
    set -a
    source "/config/.env.${NPS_PROFILE}"
    set +a
fi

# =============================================================================
# Slurm / Munge Setup (for BPS job submission)
# =============================================================================

# Pick up shared munge key from cluster volume
if [[ -f /shared-munge/munge.key ]]; then
    echo "[NPS] Loading shared munge key..."
    cp /shared-munge/munge.key /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
    munged --force 2>/dev/null && echo "[NPS] munged started" || echo "[NPS] munged failed (Slurm commands may not work)"
elif [[ -f /etc/munge/munge.key ]]; then
    echo "[NPS] Starting munge with local key..."
    chown munge:munge /etc/munge/munge.key 2>/dev/null || true
    chmod 400 /etc/munge/munge.key 2>/dev/null || true
    munged --force 2>/dev/null && echo "[NPS] munged started" || echo "[NPS] munged failed (Slurm commands may not work)"
fi

# =============================================================================
# Environment Validation
# =============================================================================

echo "[NPS] Environment:"
echo "  REPO=${REPO}"
echo "  RAW_PARENT_DIR=${RAW_PARENT_DIR}"
echo "  REFCAT_REPO=${REFCAT_REPO}"
echo "  INSTRUMENT_DIR=${INSTRUMENT_DIR}"
echo "  STIPS_DEFAULTS=${STIPS_DEFAULTS}"

# Verify critical paths exist (warnings only, don't fail)
if [[ ! -d "${REPO}" ]]; then
    echo "[NPS] WARNING: REPO directory does not exist: ${REPO}"
fi

if [[ ! -d "${RAW_PARENT_DIR}" ]]; then
    echo "[NPS] WARNING: RAW_PARENT_DIR directory does not exist: ${RAW_PARENT_DIR}"
fi

# =============================================================================
# Dashboard (background)
# =============================================================================

NPS_DASHBOARD=${NPS_DASHBOARD:-true}
NPS_DASHBOARD_PORT=${NPS_DASHBOARD_PORT:-8080}
NPS_LOGS_DIR=${NPS_LOGS_DIR:-/opt/nps/logs}

if [[ "${NPS_DASHBOARD}" == "true" ]]; then
    mkdir -p "${NPS_LOGS_DIR}"
    echo "[NPS] Starting dashboard on port ${NPS_DASHBOARD_PORT} (logs: ${NPS_LOGS_DIR})"
    python3 -c "
import uvicorn
from stips.dashboard import create_app
from pathlib import Path
app = create_app(Path('${NPS_LOGS_DIR}'))
uvicorn.run(app, host='0.0.0.0', port=${NPS_DASHBOARD_PORT}, log_level='warning')
" > "${NPS_LOGS_DIR}/dashboard.log" 2>&1 &
fi

# =============================================================================
# Execute Command
# =============================================================================

echo "[NPS] Executing: $@"
exec "$@"
