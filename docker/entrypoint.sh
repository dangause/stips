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
# Execute Command
# =============================================================================

echo "[NPS] Executing: $@"
exec "$@"
