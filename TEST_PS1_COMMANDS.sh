#!/usr/bin/env bash
#
# PS1 Template Test Commands for 2023ixf
#
# This script contains all commands to test PS1 template ingestion
# You can run sections individually or the whole script
#

set -e  # Exit on error

echo "========================================="
echo "PS1 Template Testing for 2023ixf"
echo "========================================="
echo ""

# ==========================================
# STEP 0: Setup Environment
# ==========================================
echo "STEP 0: Setting up environment..."
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Source the recalib environment
set -a
source .env.recalib
set +a

echo "  REPO: $REPO"
echo "  2023ixf RA/Dec: $IXFI_RA / $IXFI_DEC"
echo ""

# ==========================================
# STEP 1: Setup LSST Stack
# ==========================================
echo "STEP 1: Setting up LSST stack..."

cd $STACK_DIR
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

echo "  LSST stack loaded"
echo ""

# ==========================================
# STEP 2: Create New Butler Repo
# ==========================================
echo "STEP 2: Creating new Butler repository..."

if [[ -d "$REPO" ]]; then
    echo "  WARNING: Repo already exists at $REPO"
    echo "  To start fresh, run: rm -rf $REPO"
    read -p "  Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Aborted."
        exit 1
    fi
else
    echo "  Creating repo at: $REPO"
    butler create $REPO
fi

echo ""

# ==========================================
# STEP 3: Register Instrument & Skymap
# ==========================================
echo "STEP 3: Registering instrument and skymap..."

# Register instrument
butler register-instrument $REPO lsst.obs.nickel.Nickel

# Register skymap
echo "  Registering skymap: $SKYMAP_NAME"
butler register-skymap $REPO \
    -C $OBS_NICKEL/configs/makeSkyMap.py

# Verify skymap
echo "  Verifying skymap..."
butler query-datasets $REPO skyMap --collections "skymaps" || true

echo ""

# ==========================================
# STEP 3: Check PS1 Coverage
# ==========================================
echo "STEP 3: Checking PS1 coverage for 2023ixf..."

$OBS_NICKEL/scripts/utilities/check_template_coverage.sh \
    --ra $IXFI_RA \
    --dec $IXFI_DEC \
    --band r \
    --check-ps1

echo ""

# ==========================================
# STEP 4: Ingest PS1 Templates (r and i bands)
# ==========================================
echo "STEP 4: Ingesting PS1 templates..."

for BAND in r i; do
    echo "  Ingesting PS1 ${BAND}-band template for 2023ixf..."

    $OBS_NICKEL/scripts/pipeline/08_ingest_ps1_template.sh \
        --ra $IXFI_RA \
        --dec $IXFI_DEC \
        --band $BAND \
        --collection templates/ps1/2023ixf/$BAND \
        --size $PS1_CUTOUT_SIZE \
        --output-dir $OBS_NICKEL/ps1_templates/2023ixf

    echo ""
done

echo ""

# ==========================================
# STEP 5: Verify PS1 Template Ingestion
# ==========================================
echo "STEP 5: Verifying PS1 template ingestion..."

echo "  Checking template collections..."
butler query-collections $REPO | grep "templates/ps1"

echo ""
echo "  Checking template datasets..."
butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/2023ixf/*"

echo ""
echo "  Checking template metadata..."
python $OBS_NICKEL/packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py \
    list --repo $REPO --source ps1

echo ""

# ==========================================
# STEP 6: Transfer Data from Old Repo (OPTIONAL)
# ==========================================
echo "STEP 6: Transferring data from old 2023ixf repo (OPTIONAL)..."
echo ""

# Check if user wants to transfer existing data
if [[ -n "${OLD_2023IXF_REPO:-}" ]]; then
    echo "  Transferring from: $OLD_2023IXF_REPO"
    echo "  To: $REPO"
    echo ""

    # Transfer calibrations
    echo "  Transferring calibrations..."
    butler transfer-datasets "$OLD_2023IXF_REPO" "$REPO" \
        --collections 'Nickel/calib/*' \
        --register-dataset-types \
        --transfer symlink || true

    # Transfer raw data for 2023ixf
    echo "  Transferring raw 2023ixf data..."
    butler transfer-datasets "$OLD_2023IXF_REPO" "$REPO" \
        --collections 'Nickel/raw/2023*' \
        --where "exposure.target_name='2023ixf'" \
        --register-dataset-types \
        --transfer symlink || true

    # Transfer processed data
    echo "  Transferring processed 2023ixf data..."
    butler transfer-datasets "$OLD_2023IXF_REPO" "$REPO" \
        --collections 'Nickel/runs/2023*/processCcd/*' \
        --where "exposure.target_name='2023ixf'" \
        --register-dataset-types \
        --transfer symlink || true

    echo "  → Data transfer complete!"
    echo ""
else
    echo "  To transfer existing 2023ixf data, set OLD_2023IXF_REPO and re-run:"
    echo ""
    echo "  export OLD_2023IXF_REPO=/path/to/your/2023ixf/repo"
    echo "  ./TEST_PS1_COMMANDS.sh"
    echo ""
    echo "  Or add to .env.recalib:"
    echo "  OLD_2023IXF_REPO=/path/to/your/2023ixf/repo"
    echo ""
    echo "  Press Enter to continue without transferring..."
    read
fi

echo ""

# ==========================================
# STEP 7: Test DIA with PS1 Template
# ==========================================
echo "STEP 7: Testing DIA with PS1 templates (requires processed science data)..."
echo ""
echo "  If you have science data for 2023ixf, run DIA:"
echo ""
echo "  # For a specific night (example: May 20, 2023)"
echo "  $OBS_NICKEL/scripts/pipeline/40_diff_imaging.sh \\"
echo "    --night 20230520 \\"
echo "    --template templates/ps1/2023ixf/r \\"
echo "    --object 2023ixf \\"
echo "    --band r"
echo ""
echo "  # Or use auto-discovery with PS1 preference"
echo "  $OBS_NICKEL/scripts/pipeline/40_diff_imaging.sh \\"
echo "    --night 20230520 \\"
echo "    --prefer-ps1 --auto-template \\"
echo "    --object 2023ixf \\"
echo "    --band r"
echo ""

# ==========================================
# SUMMARY
# ==========================================
echo "========================================="
echo "PS1 Template Test Setup Complete!"
echo "========================================="
echo ""
echo "Summary:"
echo "  ✓ Butler repo created: $REPO"
echo "  ✓ Skymap registered: $SKYMAP_NAME"
echo "  ✓ PS1 templates ingested for 2023ixf (r, i bands)"
echo ""
echo "Next steps:"
echo "  1. Import your existing 2023ixf processed data (see STEP 6)"
echo "  2. Run DIA with PS1 templates (see STEP 7)"
echo "  3. Compare results with internal templates"
echo ""
echo "Useful commands:"
echo "  # List all collections"
echo "  butler query-collections $REPO"
echo ""
echo "  # View PS1 templates"
echo "  butler query-datasets $REPO template_coadd --collections 'templates/ps1/*'"
echo ""
echo "  # View template metadata"
echo "  python packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/template_metadata.py \\"
echo "    list --repo $REPO --source ps1 --verbose"
echo ""
