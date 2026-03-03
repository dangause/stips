#!/bin/bash
# Nickel Processing Suite Container Entrypoint
#
# This script:
# 1. Sources the LSST stack
# 2. Sets up obs_nickel and obs_nickel_data
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

# Setup obs_nickel
if [[ -d "${OBS_NICKEL}" ]]; then
    echo "[NPS] Setting up obs_nickel from ${OBS_NICKEL}"
    setup -r "${OBS_NICKEL}" obs_nickel 2>/dev/null || true
fi

# Setup obs_nickel_data
if [[ -d "${OBS_NICKEL_DATA}" ]]; then
    echo "[NPS] Setting up obs_nickel_data from ${OBS_NICKEL_DATA}"
    setup -r "${OBS_NICKEL_DATA}" obs_nickel_data 2>/dev/null || true
fi

# Add data_tools to PYTHONPATH
DATA_TOOLS_SRC="${NPS_ROOT}/packages/data_tools/src"
if [[ -d "${DATA_TOOLS_SRC}" ]]; then
    export PYTHONPATH="${DATA_TOOLS_SRC}:${PYTHONPATH:-}"
fi

# Ensure conda bin is in PATH (for pip-installed scripts like 'nickel')
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
echo "  OBS_NICKEL=${OBS_NICKEL}"

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
from obs_nickel_data_tools.dashboard import create_app
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
