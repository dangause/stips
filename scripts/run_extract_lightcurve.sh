#!/usr/bin/env bash
# run_extract_lightcurve.sh - Wrapper to run extract_lightcurve.py with LSST environment

set -a
source "$(dirname "$0")/../.env"
set +a

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

# Run the Python script with all arguments
/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$OBS_NICKEL/scripts/extract_lightcurve.py" "$@"
