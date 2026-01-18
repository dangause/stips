#!/bin/bash
# example_run_nickel_colorterms.sh
#
# Example script to compute Nickel spline-based color terms
# Adapt paths to your local setup

set -e  # Exit on error

# ============================================================================
# CONFIGURATION - EDIT THESE PATHS
# ============================================================================

# Path to Monster throughput directory
# Should contain files like: total_g.dat, total_r.dat, total_i.dat, etc.
# Or: total_comcam_g.ecsv, total_comcam_r.ecsv, etc.
MONSTER_THROUGHPUT_DIR="/path/to/the_monster/data/throughputs"

# Output directory for color term files
OUTPUT_DIR="./nickel_colorterms_output"

# Number of spline nodes (4 is good default, 6-8 for more flexibility)
N_NODES=4

# ============================================================================
# SETUP
# ============================================================================

echo "========================================================================"
echo "Nickel Spline-Based Color Term Calculator"
echo "========================================================================"
echo ""

# Check if Monster throughput directory exists
if [ ! -d "$MONSTER_THROUGHPUT_DIR" ]; then
    echo "ERROR: Monster throughput directory not found:"
    echo "  $MONSTER_THROUGHPUT_DIR"
    echo ""
    echo "Please edit this script and set MONSTER_THROUGHPUT_DIR to the"
    echo "location of your Monster throughput files."
    echo ""
    echo "These files should be in:"
    echo "  the_monster/data/throughputs/"
    echo ""
    exit 1
fi

# Check for required Python packages
echo "Checking Python dependencies..."
python -c "import numpy, scipy, matplotlib, astropy, fitsio, astroquery, yaml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Missing required Python packages."
    echo "Please install:"
    echo "  pip install numpy scipy matplotlib astropy fitsio astroquery pyyaml"
    echo ""
    echo "For FGCM stellar templates:"
    echo "  pip install fgcm"
    echo ""
    exit 1
fi

echo "All dependencies found!"
echo ""

# ============================================================================
# RUN COLOR TERM CALCULATION
# ============================================================================

echo "Running color term calculation..."
echo "  Monster throughputs: $MONSTER_THROUGHPUT_DIR"
echo "  Output directory:    $OUTPUT_DIR"
echo "  Number of nodes:     $N_NODES"
echo ""

python nickel_colorterm_fitter.py \
    --monster-throughput-dir "$MONSTER_THROUGHPUT_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --n-nodes $N_NODES \
    --bands B V R I \
    --plots \
    --overwrite

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo "========================================================================"
echo "SUCCESS!"
echo "========================================================================"
echo ""
echo "Color term files written to: $OUTPUT_DIR/"
echo ""
echo "Generated files:"
echo "  - YAML files (spline parameters)"
echo "  - Config files (polynomial approximations)"
echo "  - QA plots (PNG images)"
echo "  - Summary text file"
echo ""
echo "Next steps:"
echo "  1. Review QA plots in $OUTPUT_DIR/"
echo "  2. Check nickel_colorterms_summary.txt"
echo "  3. Integrate into obs_nickel/configs/colorterms.py"
echo ""
echo "To view plots:"
echo "  open $OUTPUT_DIR/*.png"
echo ""
