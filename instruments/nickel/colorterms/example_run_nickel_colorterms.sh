#!/bin/bash
# Driver script for the synthetic Nickel colorterm fitter.
#
# Edit the paths below for your local setup, then run:
#     ./example_run_nickel_colorterms.sh
#
# Inputs:
#   - Monster throughput files (total_<band>.dat or total_comcam_<band>.ecsv).
# Outputs (in $OUTPUT_DIR):
#   - Per-band YAML files containing spline parameters
#   - Per-band PNG QA plots
#   - Per-band TXT files with polynomial approximations
#   - A summary file listing everything generated

set -euo pipefail

# ----------------------------------------------------------------------
# Configuration — edit for your environment
# ----------------------------------------------------------------------

MONSTER_THROUGHPUT_DIR="/path/to/the_monster/data/throughputs"
OUTPUT_DIR="./nickel_colorterms_output"
N_NODES=4

# ----------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------

if [ ! -d "$MONSTER_THROUGHPUT_DIR" ]; then
    echo "Monster throughput directory not found: $MONSTER_THROUGHPUT_DIR" >&2
    echo "Set MONSTER_THROUGHPUT_DIR at the top of this script." >&2
    exit 1
fi

if ! python -c "import numpy, scipy, matplotlib, astropy, fitsio, astroquery, yaml" 2>/dev/null; then
    echo "Missing Python dependencies." >&2
    echo "  pip install numpy scipy matplotlib astropy fitsio astroquery pyyaml" >&2
    echo "  pip install fgcm   # for stellar templates" >&2
    exit 1
fi

# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------

python nickel_colorterm_fitter.py \
    --monster-throughput-dir "$MONSTER_THROUGHPUT_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --n-nodes "$N_NODES" \
    --bands B V R I \
    --plots \
    --overwrite

echo "Color terms written to $OUTPUT_DIR/"
echo "Next: convert to LSST format with convert_to_lsst_colorterms.py"
