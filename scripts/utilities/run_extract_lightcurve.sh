#!/usr/bin/env bash
# run_extract_lightcurve.sh - Wrapper to run extract_lightcurve.py with LSST environment

# Get the absolute path to the obs_nickel repository
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBS_NICKEL="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Check if .env.2020wnt or .env.2023ixf exists and use it, otherwise use default paths
if [ -f "$OBS_NICKEL/.env.2020wnt" ]; then
    set -a
    source "$OBS_NICKEL/.env.2020wnt"
    set +a
elif [ -f "$OBS_NICKEL/.env.2023ixf" ]; then
    set -a
    source "$OBS_NICKEL/.env.2023ixf"
    set +a
elif [ -f "$OBS_NICKEL/.env" ]; then
    set -a
    source "$OBS_NICKEL/.env"
    set +a
fi

# Set default STACK_DIR if not set
STACK_DIR="${STACK_DIR:-/Users/dangause/Developer/lick/lsst/lsst_stack}"

# Check if STACK_DIR exists
if [ ! -d "$STACK_DIR" ]; then
    echo "Error: STACK_DIR not found: $STACK_DIR"
    exit 1
fi

# Load LSST environment
cd "$STACK_DIR"
source loadLSST.bash
setup lsst_distrib
setup obs_nickel || true

# Change back to obs_nickel directory before running the script
cd "$OBS_NICKEL"

# Run the Python script with all arguments
python "$OBS_NICKEL/scripts/python/pipeline_tools/extract_lightcurve.py" "$@"
