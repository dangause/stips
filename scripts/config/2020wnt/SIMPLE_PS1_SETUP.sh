#!/usr/bin/env bash
#
# SN 2020wnt DIA with PS1 Template - Simplified Setup
# Uses run_full_transient_pipeline.sh + PS1 template
#

set -euo pipefail

cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel

# ==========================================
# 1. Create new repo and install astroquery
# ==========================================

export NEW_REPO="/Users/dangause/Developer/lick/lsst/data/nickel/2020wnt_ps1_repo"

butler create "$NEW_REPO"
butler register-instrument "$NEW_REPO" lsst.obs.nickel.Nickel

# Install astroquery (one-time)
pip install astroquery 2>/dev/null || true

# ==========================================
# 2. Ingest PS1 template
# ==========================================

REPO="$NEW_REPO" ./scripts/pipeline/08_ingest_ps1_template.sh \
    --ra 83.8145 \
    --dec 3.0847 \
    --band r \
    --collection "templates/ps1/r"

# ==========================================
# 3. Run full pipeline (skip template building)
# ==========================================

REPO="$NEW_REPO" ./scripts/pipeline/run_full_transient_pipeline.sh \
    --template-nights scripts/config/2020wnt/template_nights.txt \
    --dia-nights scripts/config/2020wnt/sn_nights.txt \
    --band r \
    --transient-name "SN2020wnt" \
    --ra 83.8145 \
    --dec 3.0847 \
    --skip-download \
    --skip-template \
    --jobs 8 \
    --output-dir ./sn2020wnt_ps1_results

# NOTE: After this completes, manually run DIA with PS1 template
# since run_full_transient_pipeline doesn't have a --template-collection flag yet

echo ""
echo "=========================================="
echo "Pipeline complete! Now run DIA manually:"
echo "=========================================="
echo ""
echo "for night in 20220105 20220108 20220110 20220118 20220124 20220126 20220129 20220208 20220212; do"
echo "    REPO=\"$NEW_REPO\" ./scripts/pipeline/40_diff_imaging.sh \\"
echo "        --night \"\$night\" \\"
echo "        --template \"templates/ps1/r\" \\"
echo "        --band r \\"
echo "        --object \"2020wnt\" \\"
echo "        -j 8"
echo "done"
echo ""
