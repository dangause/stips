#!/usr/bin/env bash
#
# test_recal_2020wnt.sh - Test DRP recalibration pipeline with 2020wnt data
#
# This script runs the full recalibration pipeline on a subset of 2020wnt nights.
# Good test case: 7 nights, multi-band observations, covers Dec 2020 - Mar 2021
#

set -euo pipefail

# Configuration
NIGHTS_FILE="nights_2020wnt_recal_test.txt"
TRACT=1825  # 2020wnt tract
BANDS="r,i,v,b"  # All bands observed
JOBS=4

# Object filter (ensures we only process 2020wnt exposures)
OBJECT="2020wnt"

echo "════════════════════════════════════════════════════════════════"
echo "  DRP Recalibration Test: 2020wnt Campaign"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Nights file: $NIGHTS_FILE"
echo "  Tract: $TRACT"
echo "  Bands: $BANDS"
echo "  Object filter: $OBJECT"
echo "  Jobs: $JOBS"
echo ""
echo "This will process 7 nights from the 2020wnt campaign:"
cat "$NIGHTS_FILE" | grep -v "^#" | grep -v "^$"
echo ""
echo "Pipeline stages:"
echo "  1. Bootstrap repository (if needed)"
echo "  2. Process calibrations (per night)"
echo "  3. Run Stage 1 science (single-visit processing)"
echo "  4. Run Stage 2 recalibration (FGCM + GBDES + PSF refit)"
echo "  5. Build coadds with recalibrated data"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Starting pipeline..."
echo ""

# Run the full pipeline
ENV_FILE=.env.recal ./scripts/pipeline/run_drp_recal.sh \
  --nights-file "$NIGHTS_FILE" \
  --tract "$TRACT" \
  --bands "$BANDS" \
  --object "$OBJECT" \
  --jobs "$JOBS" \
  "$@"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Pipeline Complete!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Check results:"
echo "  Repository: \$REPO (from .env.recal)"
echo "  Logs: \$REPO/logs/"
echo ""
echo "Verify Stage 2 outputs:"
echo "  butler query-collections \$REPO | grep 'recal/stage2'"
echo "  butler query-datasets \$REPO fgcmPhotoCalibCatalog"
echo "  butler query-datasets \$REPO gbdesAstrometricFitSkyWcsCatalog"
echo "  butler query-datasets \$REPO visit_summary --collections 'Nickel/recal/stage2/*'"
echo ""
echo "Verify coadds:"
echo "  butler query-datasets \$REPO template_coadd --collections 'Nickel/recal/coadds/*'"
echo ""
