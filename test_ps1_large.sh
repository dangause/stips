#!/usr/bin/env bash
#
# Test PS1 template with larger cutout size for better spatial coverage
#

set -euo pipefail

cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# Source test environment
set -a
source .env.recalib
set +a

echo "========================================="
echo "PS1 Large Template Test"
echo "========================================="
echo ""
echo "REPO: $REPO"
echo "Target: 2023ixf at RA=$IXFI_RA, Dec=$IXFI_DEC"
echo ""

# Ingest larger PS1 template (0.5 degrees instead of 0.3)
echo "Step 1: Ingesting larger PS1 template (0.5 degrees)..."
./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra $IXFI_RA \
    --dec $IXFI_DEC \
    --band r \
    --collection templates/ps1/2023ixf/r_large \
    --size 0.5

echo ""
echo "Step 2: Verifying template ingestion..."
cd $STACK_DIR
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel

butler query-datasets $REPO template_coadd \
    --collections "templates/ps1/2023ixf/r_large"

echo ""
echo "Step 3: Running DIA with larger PS1 template..."
cd $OBS_NICKEL

ENV_FILE=.env.recalib ./scripts/pipeline/40_diff_imaging.sh \
    --night 20230519 \
    --template templates/ps1/2023ixf/r_large \
    --band r \
    --object 2023ixf \
    -j 4

echo ""
echo "========================================="
echo "Test Complete!"
echo "========================================="
echo ""
echo "Check results:"
echo "  DIA collection: Nickel/runs/20230519/diff/*/run"
echo ""
echo "Query difference images:"
echo "  butler query-datasets $REPO difference_image \\"
echo "    --collections 'Nickel/runs/20230519/diff/*/run'"
echo ""
