#!/usr/bin/env bash
#
# Complete command sequence for SN 2020wnt DIA using PS1 templates
# Fresh repository setup (no re-downloading raw data)
#
# SN 2020wnt: RA=83.8145°, Dec=3.0847° (5h 35m 15.5s, +03° 05' 05")
# Band: R (best match with PS1 r-band)
#

# set -euo pipefail

# Source environment
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
source .env

# ==========================================
# STEP 0: Create Fresh Repository
# ==========================================

# Set new repository path (modify as needed)
export NEW_REPO="/Users/dangause/Developer/lick/lsst/butler_repo_2020wnt_ps1"
export INSTRUMENT="lsst.obs.nickel.Nickel"

echo "=========================================="
echo "Creating fresh Butler repository"
echo "Repository: $NEW_REPO"
echo "=========================================="

# Create repository
butler create "$NEW_REPO"

# Register instrument
butler register-instrument "$NEW_REPO" "$INSTRUMENT"

# ==========================================
# STEP 1: Bootstrap - Ingest Reference Catalogs & Skymap
# ==========================================

echo ""
echo "=========================================="
echo "Bootstrap: Reference Catalogs & Skymap"
echo "=========================================="

# Setup LSST stack
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel

cd "$OBS_NICKEL"

# Run bootstrap (this will ingest refcats and register skymap)
# NOTE: You'll need to modify 00_bootstrap_repo.sh to use $NEW_REPO instead of $REPO
# Or run the refcat/skymap steps manually:

# Option A: Modify bootstrap script temporarily
# sed "s|\$REPO|$NEW_REPO|g" scripts/pipeline/00_bootstrap_repo.sh > /tmp/bootstrap_temp.sh
# chmod +x /tmp/bootstrap_temp.sh
# /tmp/bootstrap_temp.sh

# Option B: Manual refcat/skymap setup (recommended for fresh repo)
echo "Setting up reference catalogs..."

# If you have pre-ingested refcats, you can copy the collection chains:
# butler collection-chain "$NEW_REPO" refcats <your_refcat_collections>

# Or run the refcat ingestion from 00_bootstrap_repo.sh manually
# For now, assuming you'll copy from existing repo or re-run bootstrap

echo "MANUAL STEP REQUIRED:"
echo "  1. Ingest reference catalogs (the_monster, PS1, or Gaia DR3)"
echo "  2. Register skymap 'nickelRings-v1'"
echo ""
echo "Quick option: Copy from existing repo:"
echo "  # Copy refcats"
echo "  butler collection-chain $NEW_REPO refcats <existing_refcat_collection>"
echo ""
echo "  # Copy skymap"
echo "  butler transfer-datasets $REPO $NEW_REPO skyMap --collections skymaps"
echo ""
read -p "Press Enter when bootstrap is complete..."

# ==========================================
# STEP 2: Ingest PS1 R-band Template
# ==========================================

echo ""
echo "=========================================="
echo "Ingesting PS1 R-band Template"
echo "=========================================="

# SN 2020wnt coordinates
SN_RA=83.8145
SN_DEC=3.0847
BAND="r"

# Install astroquery if needed
echo "Checking for astroquery..."
python -c "import astroquery" 2>/dev/null || {
    echo "Installing astroquery..."
    pip install astroquery
}

# Ingest PS1 template
# This will:
# - Download PS1 r-band stacked image for the field
# - Convert to LSST Exposure format
# - Ingest as template_coadd
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra "$SN_RA" \
    --dec "$SN_DEC" \
    --band "$BAND" \
    --collection "templates/ps1/r/sn2020wnt" \
    --size 0.15 \
    --output-dir "./ps1_templates_2020wnt"

echo ""
echo "Verifying PS1 template ingestion..."
butler query-datasets "$NEW_REPO" template_coadd \
    --collections "templates/ps1/r/sn2020wnt"

echo ""
read -p "Press Enter to continue to calibration processing..."

# ==========================================
# STEP 3: Process Calibrations (Per Night)
# ==========================================

echo ""
echo "=========================================="
echo "Processing Calibrations"
echo "=========================================="

# Template nights (pre-SN, for reference - but we're using PS1 template)
TEMPLATE_NIGHTS=(
    20201207
    20201219
    20210208
    20210218
)

# SN observation nights
SN_NIGHTS=(
    20220105
    20220108
    20220110
    20220118
    20220124
    20220126
    20220129
    20220208
    20220212
)

# Combine all nights for calibration processing
ALL_NIGHTS=("${TEMPLATE_NIGHTS[@]}" "${SN_NIGHTS[@]}")

# Process calibrations for each night
# NOTE: Raw data must already exist in $RAW_PARENT_DIR
for night in "${ALL_NIGHTS[@]}"; do
    echo ""
    echo "Processing calibrations for night: $night"

    # Check if raw data exists
    if [[ ! -d "$RAW_PARENT_DIR/$night/raw" ]]; then
        echo "WARNING: Raw data not found for $night, skipping"
        continue
    fi

    # Run calibration processing
    # This uses your existing 10_calibs.sh but with new repo
    REPO="$NEW_REPO" ./scripts/pipeline/10_calibs.sh --night "$night"
done

echo ""
echo "Calibration processing complete"
read -p "Press Enter to continue to science processing..."

# ==========================================
# STEP 4: Process Science Images (Single-Visit)
# ==========================================

echo ""
echo "=========================================="
echo "Processing Science Images (processCcd)"
echo "=========================================="

# Process only R-band science images
for night in "${SN_NIGHTS[@]}"; do
    echo ""
    echo "Processing science for night: $night"

    if [[ ! -d "$RAW_PARENT_DIR/$night/raw" ]]; then
        echo "WARNING: Raw data not found for $night, skipping"
        continue
    fi

    # Run science processing (processCcd)
    # Filter by object=2020wnt and skip coadds (we'll use PS1 template)
    REPO="$NEW_REPO" ./scripts/pipeline/20_science.sh \
        --night "$night" \
        --object "2020wnt" \
        --skip-coadds \
        -j 8
done

echo ""
echo "Science processing complete"
read -p "Press Enter to continue to DIA..."

# ==========================================
# STEP 5: Run Difference Imaging with PS1 Template
# ==========================================

echo ""
echo "=========================================="
echo "Running Difference Imaging (DIA)"
echo "=========================================="

# Run DIA for each SN night using PS1 template
for night in "${SN_NIGHTS[@]}"; do
    echo ""
    echo "Running DIA for night: $night"

    # Check if processCcd outputs exist
    night_outputs=$(butler query-datasets "$NEW_REPO" preliminary_visit_image \
        --collections "Nickel/runs/$night/processCcd/*/run" \
        --where "instrument='Nickel' AND day_obs=$night" 2>/dev/null | wc -l)

    if [[ "$night_outputs" -lt 2 ]]; then
        echo "WARNING: No processCcd outputs for $night, skipping"
        continue
    fi

    # Run DIA with PS1 template
    REPO="$NEW_REPO" ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" \
        --template "templates/ps1/r/sn2020wnt" \
        --band r \
        --object "2020wnt" \
        -j 8
done

echo ""
echo "DIA processing complete"

# ==========================================
# STEP 6: Extract Light Curve
# ==========================================

echo ""
echo "=========================================="
echo "Extracting Light Curve"
echo "=========================================="

# Extract light curve for SN 2020wnt
OUTPUT_DIR="./sn2020wnt_ps1_results"
mkdir -p "$OUTPUT_DIR"

# Find all DIA output collections
DIA_COLLECTIONS=$(butler query-collections "$NEW_REPO" | grep "Nickel/runs/.*/diff/.*/run" | paste -sd, -)

echo "DIA collections: $DIA_COLLECTIONS"

# Extract light curve
python scripts/python/pipeline_tools/extract_lightcurve.py \
    --repo "$NEW_REPO" \
    --collection "$DIA_COLLECTIONS" \
    --ra "$SN_RA" \
    --dec "$SN_DEC" \
    --radius 1.0 \
    --band r \
    --min-snr 3.0 \
    --output "$OUTPUT_DIR/sn2020wnt_lightcurve_ps1template.ecsv"

echo ""
echo "Light curve saved to: $OUTPUT_DIR/sn2020wnt_lightcurve_ps1template.ecsv"

# ==========================================
# STEP 7: Quality Assessment
# ==========================================

echo ""
echo "=========================================="
echo "Quality Assessment"
echo "=========================================="

# Generate quality reports for each night
for night in "${SN_NIGHTS[@]}"; do
    echo "Generating quality report for $night..."

    python scripts/python/pipeline_tools/assess_dia_quality.py \
        --repo "$NEW_REPO" \
        --collection "Nickel/runs/$night/diff/*/run" \
        --night "$night" \
        --output "$OUTPUT_DIR/dia_quality_$night.txt" \
        2>/dev/null || echo "  (No DIA outputs for $night)"
done

# ==========================================
# Summary
# ==========================================

echo ""
echo "=========================================="
echo "SN 2020wnt PS1 Template DIA Complete!"
echo "=========================================="
echo ""
echo "Repository:        $NEW_REPO"
echo "SN coordinates:    RA=$SN_RA, Dec=$SN_DEC"
echo "PS1 template:      templates/ps1/r/sn2020wnt"
echo "Results directory: $OUTPUT_DIR"
echo ""
echo "Output files:"
echo "  - Light curve:     $OUTPUT_DIR/sn2020wnt_lightcurve_ps1template.ecsv"
echo "  - Quality reports: $OUTPUT_DIR/dia_quality_*.txt"
echo "  - PS1 template:    ./ps1_templates_2020wnt/"
echo ""
echo "Next steps:"
echo "  1. Plot light curve: topcat $OUTPUT_DIR/sn2020wnt_lightcurve_ps1template.ecsv"
echo "  2. Inspect difference images with DS9 or Firefly"
echo "  3. Compare with Nickel template results (if available)"
echo ""
echo "Query DIA outputs:"
echo "  butler query-datasets $NEW_REPO difference_image \\"
echo "    --collections 'Nickel/runs/*/diff/*/run'"
echo ""
