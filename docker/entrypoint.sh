#!/bin/bash
# Small Telescope Image Processing Suite Container Entrypoint
#
# This script:
# 1. Sources the LSST stack
# 2. Sets up obs_stips + the active instrument's EUPS packages discovered under
#    INSTRUMENT_DIR (instrument itself is declarative, loaded by path)
# 3. Loads environment from mounted config if present
# 4. Executes the provided command

set -e

# =============================================================================
# LSST Stack Activation
# =============================================================================

echo "[STIPS] Activating LSST Science Pipelines..."
source "${STACK_DIR}/loadLSST.bash"
setup lsst_distrib

# =============================================================================
# STIPS Package Setup
# =============================================================================

# Setup obs_stips (generic LSST glue). The nickel instrument is declarative
# and loaded by path from INSTRUMENT_DIR — no EUPS setup required.
OBS_STIPS="${OBS_STIPS:-${STIPS_ROOT}/packages/obs_stips}"
if [[ -d "${OBS_STIPS}" ]]; then
    echo "[STIPS] Setting up obs_stips from ${OBS_STIPS}"
    setup -r "${OBS_STIPS}" obs_stips 2>/dev/null || true
fi

# Set up the active instrument's EUPS packages (curated calibration data, test
# fixtures, ...). Any subdirectory of INSTRUMENT_DIR that contains a
# ups/<name>.table is an instrument-owned EUPS product; declare/setup it by its
# table (product) name -- which comes from the table filename, not the directory
# (e.g. dir `testdata/` ships product `testdata_nickel`). This is generic: a fork
# sets INSTRUMENT_DIR (baked as an image ENV) and its co-located packages are
# picked up with no per-instrument edits here.
if [[ -d "${INSTRUMENT_DIR}" ]]; then
    for pkg_dir in "${INSTRUMENT_DIR}"/*/; do
        [[ -d "${pkg_dir}ups" ]] || continue
        for tbl in "${pkg_dir}ups/"*.table; do
            [[ -e "$tbl" ]] || continue
            pkg="$(basename "$tbl" .table)"
            echo "[STIPS] Setting up ${pkg} from ${pkg_dir%/}"
            setup -r "${pkg_dir%/}" "$pkg" 2>/dev/null || true
        done
    done
fi

# Add stips to PYTHONPATH
STIPS_SRC="${STIPS_ROOT}/packages/stips/src"
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
    echo "[STIPS] Loading configuration from /config/.env"
    set -a
    source /config/.env
    set +a
fi

# Load profile-specific .env if STIPS_PROFILE is set
if [[ -n "${STIPS_PROFILE}" && -f "/config/.env.${STIPS_PROFILE}" ]]; then
    echo "[STIPS] Loading profile configuration from /config/.env.${STIPS_PROFILE}"
    set -a
    source "/config/.env.${STIPS_PROFILE}"
    set +a
fi

# =============================================================================
# Slurm / Munge Setup (for BPS job submission)
# =============================================================================

# Pick up shared munge key from cluster volume
if [[ -f /shared-munge/munge.key ]]; then
    echo "[STIPS] Loading shared munge key..."
    cp /shared-munge/munge.key /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
    munged --force 2>/dev/null && echo "[STIPS] munged started" || echo "[STIPS] munged failed (Slurm commands may not work)"
elif [[ -f /etc/munge/munge.key ]]; then
    echo "[STIPS] Starting munge with local key..."
    chown munge:munge /etc/munge/munge.key 2>/dev/null || true
    chmod 400 /etc/munge/munge.key 2>/dev/null || true
    munged --force 2>/dev/null && echo "[STIPS] munged started" || echo "[STIPS] munged failed (Slurm commands may not work)"
fi

# =============================================================================
# Environment Validation
# =============================================================================

echo "[STIPS] Environment:"
echo "  REPO=${REPO}"
echo "  RAW_PARENT_DIR=${RAW_PARENT_DIR}"
echo "  REFCAT_REPO=${REFCAT_REPO}"
echo "  INSTRUMENT_DIR=${INSTRUMENT_DIR}"
echo "  STIPS_DEFAULTS=${STIPS_DEFAULTS}"

# Verify critical paths exist (warnings only, don't fail)
if [[ ! -d "${REPO}" ]]; then
    echo "[STIPS] WARNING: REPO directory does not exist: ${REPO}"
fi

if [[ ! -d "${RAW_PARENT_DIR}" ]]; then
    echo "[STIPS] WARNING: RAW_PARENT_DIR directory does not exist: ${RAW_PARENT_DIR}"
fi

# =============================================================================
# Dashboard (background)
# =============================================================================

STIPS_DASHBOARD=${STIPS_DASHBOARD:-true}
STIPS_DASHBOARD_PORT=${STIPS_DASHBOARD_PORT:-8080}
STIPS_LOGS_DIR=${STIPS_LOGS_DIR:-/opt/stips/logs}

if [[ "${STIPS_DASHBOARD}" == "true" ]]; then
    mkdir -p "${STIPS_LOGS_DIR}"
    echo "[STIPS] Starting dashboard on port ${STIPS_DASHBOARD_PORT} (logs: ${STIPS_LOGS_DIR})"
    python3 -c "
import uvicorn
from stips.dashboard import create_app
from pathlib import Path
app = create_app(Path('${STIPS_LOGS_DIR}'))
uvicorn.run(app, host='0.0.0.0', port=${STIPS_DASHBOARD_PORT}, log_level='warning')
" > "${STIPS_LOGS_DIR}/dashboard.log" 2>&1 &
fi

# =============================================================================
# Execute Command
# =============================================================================

echo "[STIPS] Executing: $@"
exec "$@"
