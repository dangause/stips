#!/usr/bin/env bash
#
# test_nickel_template_dia.sh - End-to-end test of DIA with Nickel-built templates
#
# This script demonstrates the complete workflow for running difference imaging
# using Nickel telescope deep coadd templates (NOT external PS1 templates).
#
# Workflow:
#   1. Process calibrations for template nights
#   2. Process science images for template nights
#   3. Build deep coadd template from multiple nights
#   4. Process calibrations for science night
#   5. Process science images for science night
#   6. Run difference imaging (science - template)
#   7. Extract light curve / assess quality
#
# Usage:
#   ./test_nickel_template_dia.sh [--repo REPO]
#
# Requirements:
#   - Raw data already downloaded and ingested (01_download_archive.sh)
#   - Reference catalogs and skymap configured (00_bootstrap_repo.sh)

set -euo pipefail

# Load environment
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
else
    echo "ERROR: .env file not found. Run from obs_nickel root directory."
    exit 1
fi

########## CONFIGURATION ##########

# Repository to use (default from .env, or override with --repo)
TEST_REPO="${REPO:-}"

# Parse command line
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) TEST_REPO="${2:-}"; shift 2;;
        -h|--help)
            cat <<USAGE
Usage: $0 [options]

Test DIA workflow with Nickel-built template coadds.

Options:
  --repo REPO    Butler repository path (default: from .env)
  -h, --help     Show this help message

Example:
  # Use default repo from .env
  $0

  # Use specific test repo
  $0 --repo /path/to/test_repo

USAGE
            exit 0;;
        *) echo "Unknown option: $1"; exit 2;;
    esac
done

[[ -n "$TEST_REPO" ]] || { echo "ERROR: REPO not set in .env or --repo"; exit 2; }

########## TEST CONFIGURATION ##########

# Template nights (pre-transient, for building deep template)
# Choose nights with good seeing, no clouds, multiple in same band
TEMPLATE_NIGHTS=(
    20201207
    20201219
)

# Science nights (contains transient/variable, or just recent data for testing)
# These will be subtracted against the template
SCIENCE_NIGHTS=(
    20220105
)

# Target configuration
TRACT=1099                # Tract that covers your target field
BAND="r"                  # Band for template and science
TARGET_OBJECT="2020wnt"   # Optional: filter by object name (leave empty for all)
TARGET_RA=83.8145         # For light curve extraction
TARGET_DEC=3.0847

# Processing parameters
JOBS=8                    # Parallelization

########## DIRECTORIES ##########

OUTPUT_DIR="./nickel_template_dia_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

LOG_FILE="$OUTPUT_DIR/workflow.log"

echo "================================================================================"
echo "=== Nickel Template DIA Test Workflow ==="
echo "================================================================================"
echo "Repository:       $TEST_REPO"
echo "Template nights:  ${TEMPLATE_NIGHTS[*]}"
echo "Science nights:   ${SCIENCE_NIGHTS[*]}"
echo "Tract:            $TRACT"
echo "Band:             $BAND"
echo "Target:           ${TARGET_OBJECT:-all objects}"
echo "Output:           $OUTPUT_DIR"
echo "================================================================================"
echo ""

# Redirect all output to log file and terminal
exec > >(tee -a "$LOG_FILE")
exec 2>&1

########## ENVIRONMENT SETUP ##########

echo "[setup] Activating LSST stack..."
cd "$STACK_DIR"
set +u
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
set -u

cd "$OBS_NICKEL"

INSTRUMENT="lsst.obs.nickel.Nickel"
butler register-instrument "$TEST_REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

########## STEP 1: Process Template Night Calibrations ##########

echo ""
echo "================================================================================"
echo "STEP 1: Processing calibrations for template nights"
echo "================================================================================"
echo ""

for night in "${TEMPLATE_NIGHTS[@]}"; do
    echo "[calibs] Processing night $night..."

    # Check if raw data exists
    if ! butler query-collections "$TEST_REPO" | grep -q "Nickel/raw/$night"; then
        echo "WARNING: No raw data found for night $night"
        echo "         Run: NIGHT=$night ./scripts/pipeline/01_download_archive.sh"
        continue
    fi

    # Run calibration processing
    REPO="$TEST_REPO" NIGHT="$night" ./scripts/pipeline/10_calibs.sh \
        --night "$night" \
        -j "$JOBS" || {
        echo "ERROR: Calibration processing failed for $night"
        exit 1
    }

    echo ""
done

########## STEP 2: Process Template Night Science Images ##########

echo ""
echo "================================================================================"
echo "STEP 2: Processing science images for template nights"
echo "================================================================================"
echo ""

for night in "${TEMPLATE_NIGHTS[@]}"; do
    echo "[science] Processing night $night..."

    # Build filter args
    FILTER_ARGS=()
    [[ -n "$TARGET_OBJECT" ]] && FILTER_ARGS+=(--object "$TARGET_OBJECT")

    # Run science processing (processCcd)
    # Skip coadds here - we'll build multi-night coadds separately
    REPO="$TEST_REPO" NIGHT="$night" ./scripts/pipeline/20_science.sh \
        --night "$night" \
        --skip-coadds \
        -j "$JOBS" \
        "${FILTER_ARGS[@]}" || {
        echo "ERROR: Science processing failed for $night"
        exit 1
    }

    echo ""
done

########## STEP 3: Build Deep Coadd Template ##########

echo ""
echo "================================================================================"
echo "STEP 3: Building deep coadd template"
echo "================================================================================"
echo ""

# Create nights file for template building
TEMPLATE_NIGHTS_FILE="$OUTPUT_DIR/template_nights.txt"
printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TEMPLATE_NIGHTS_FILE"

echo "[template] Building from nights: ${TEMPLATE_NIGHTS[*]}"
echo "[template] Tract: $TRACT, Band: $BAND"

# Build template coadd
REPO="$TEST_REPO" ./scripts/pipeline/30_coadds.sh \
    --tract "$TRACT" \
    --band "$BAND" \
    --nights-file "$TEMPLATE_NIGHTS_FILE" \
    -j "$JOBS" || {
    echo "ERROR: Template building failed"
    exit 1
}

# Find the template collection that was just created
TEMPLATE_COLLECTION=$(butler query-collections "$TEST_REPO" \
    | grep "templates/deep/tract${TRACT}/${BAND}/" \
    | tail -n1)

if [[ -z "$TEMPLATE_COLLECTION" ]]; then
    echo "ERROR: Template collection not found after building"
    exit 1
fi

echo ""
echo "[template] Created: $TEMPLATE_COLLECTION"

# Verify template has data
TEMPLATE_COUNT=$(butler query-datasets "$TEST_REPO" template_coadd \
    --collections "$TEMPLATE_COLLECTION" 2>/dev/null | wc -l || echo "0")

echo "[template] Contains $TEMPLATE_COUNT template coadds"

if [[ "$TEMPLATE_COUNT" -eq 0 ]]; then
    echo "ERROR: Template collection is empty!"
    exit 1
fi

echo ""

########## STEP 4: Process Science Night Calibrations ##########

echo ""
echo "================================================================================"
echo "STEP 4: Processing calibrations for science nights"
echo "================================================================================"
echo ""

for night in "${SCIENCE_NIGHTS[@]}"; do
    echo "[calibs] Processing night $night..."

    # Check if raw data exists
    if ! butler query-collections "$TEST_REPO" | grep -q "Nickel/raw/$night"; then
        echo "WARNING: No raw data found for night $night"
        echo "         Run: NIGHT=$night ./scripts/pipeline/01_download_archive.sh"
        continue
    fi

    # Run calibration processing
    REPO="$TEST_REPO" NIGHT="$night" ./scripts/pipeline/10_calibs.sh \
        --night "$night" \
        -j "$JOBS" || {
        echo "ERROR: Calibration processing failed for $night"
        exit 1
    }

    echo ""
done

########## STEP 5: Process Science Night Science Images ##########

echo ""
echo "================================================================================"
echo "STEP 5: Processing science images for science nights"
echo "================================================================================"
echo ""

for night in "${SCIENCE_NIGHTS[@]}"; do
    echo "[science] Processing night $night..."

    # Build filter args
    FILTER_ARGS=()
    [[ -n "$TARGET_OBJECT" ]] && FILTER_ARGS+=(--object "$TARGET_OBJECT")

    # Run science processing (processCcd)
    REPO="$TEST_REPO" NIGHT="$night" ./scripts/pipeline/20_science.sh \
        --night "$night" \
        --skip-coadds \
        -j "$JOBS" \
        "${FILTER_ARGS[@]}" || {
        echo "ERROR: Science processing failed for $night"
        exit 1
    }

    echo ""
done

########## STEP 6: Run Difference Imaging ##########

echo ""
echo "================================================================================"
echo "STEP 6: Running difference imaging (DIA)"
echo "================================================================================"
echo ""

DIA_COLLECTIONS=()

for night in "${SCIENCE_NIGHTS[@]}"; do
    echo "[DIA] Processing night $night against template $TEMPLATE_COLLECTION..."

    # Build filter args
    FILTER_ARGS=()
    [[ -n "$TARGET_OBJECT" ]] && FILTER_ARGS+=(--object "$TARGET_OBJECT")

    # Run DIA
    REPO="$TEST_REPO" NIGHT="$night" ./scripts/pipeline/40_diff_imaging.sh \
        --night "$night" \
        --template "$TEMPLATE_COLLECTION" \
        --band "$BAND" \
        --tract "$TRACT" \
        -j "$JOBS" \
        "${FILTER_ARGS[@]}" || {
        echo "ERROR: DIA processing failed for $night"
        exit 1
    }

    # Find the DIA collection that was just created
    DIA_COLL=$(butler query-collections "$TEST_REPO" \
        | grep "Nickel/runs/${night}/diff/" \
        | tail -n1)

    if [[ -n "$DIA_COLL" ]]; then
        DIA_COLLECTIONS+=("$DIA_COLL")
        echo "[DIA] Created: $DIA_COLL"
    fi

    echo ""
done

if [[ ${#DIA_COLLECTIONS[@]} -eq 0 ]]; then
    echo "ERROR: No DIA collections created"
    exit 1
fi

########## STEP 7: Extract Light Curve and Assess Quality ##########

echo ""
echo "================================================================================"
echo "STEP 7: Extracting light curve and assessing quality"
echo "================================================================================"
echo ""

# Join DIA collections with commas
DIA_CHAIN=$(IFS=','; echo "${DIA_COLLECTIONS[*]}")

echo "[lightcurve] Extracting for target at RA=$TARGET_RA, Dec=$TARGET_DEC"

# Extract light curve
LC_OUTPUT="$OUTPUT_DIR/lightcurve.ecsv"

if [[ -f "scripts/python/pipeline_tools/extract_lightcurve.py" ]]; then
    /opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python \
        scripts/python/pipeline_tools/extract_lightcurve.py \
        --repo "$TEST_REPO" \
        --collection "$DIA_CHAIN" \
        --ra "$TARGET_RA" \
        --dec "$TARGET_DEC" \
        --radius 1.0 \
        --band "$BAND" \
        --min-snr 3.0 \
        --output "$LC_OUTPUT" 2>&1 || {
        echo "WARNING: Light curve extraction failed (this is OK if no sources detected)"
    }

    if [[ -f "$LC_OUTPUT" ]]; then
        echo "[lightcurve] Saved to: $LC_OUTPUT"

        # Show summary
        echo ""
        echo "Light curve summary:"
        head -20 "$LC_OUTPUT"
    fi
else
    echo "WARNING: extract_lightcurve.py not found, skipping"
fi

echo ""

# Quality assessment
echo "[quality] Generating DIA quality metrics..."

for night in "${SCIENCE_NIGHTS[@]}"; do
    echo "  Night: $night"

    # Count DIA sources
    DIA_COUNT=$(butler query-datasets "$TEST_REPO" dia_source_unfiltered \
        --collections "Nickel/runs/$night/diff/*/run" \
        --where "instrument='Nickel'" 2>/dev/null | tail -n +2 | wc -l || echo "0")

    echo "    DIA sources: $DIA_COUNT"

    # Count difference images
    DIFF_COUNT=$(butler query-datasets "$TEST_REPO" difference_image \
        --collections "Nickel/runs/$night/diff/*/run" \
        --where "instrument='Nickel'" 2>/dev/null | tail -n +2 | wc -l || echo "0")

    echo "    Difference images: $DIFF_COUNT"
done

########## SUMMARY ##########

echo ""
echo "================================================================================"
echo "=== TEST COMPLETE ==="
echo "================================================================================"
echo ""
echo "Repository:          $TEST_REPO"
echo "Template collection: $TEMPLATE_COLLECTION"
echo "Template nights:     ${TEMPLATE_NIGHTS[*]}"
echo "Science nights:      ${SCIENCE_NIGHTS[*]}"
echo ""
echo "DIA collections:"
for coll in "${DIA_COLLECTIONS[@]}"; do
    echo "  - $coll"
done
echo ""
echo "Output directory:    $OUTPUT_DIR"
echo "Log file:            $LOG_FILE"
if [[ -f "$LC_OUTPUT" ]]; then
    echo "Light curve:         $LC_OUTPUT"
fi
echo ""
echo "================================================================================"
echo "Next Steps:"
echo "================================================================================"
echo ""
echo "1. INSPECT DIFFERENCE IMAGES:"
echo "   butler get $TEST_REPO difference_image \\"
echo "     --collections '${DIA_COLLECTIONS[0]}' \\"
echo "     --where \"instrument='Nickel' AND band='$BAND'\""
echo ""
echo "2. QUERY DIA SOURCES:"
echo "   butler query-datasets $TEST_REPO dia_source_unfiltered \\"
echo "     --collections '${DIA_COLLECTIONS[0]}'"
echo ""
echo "3. PLOT LIGHT CURVE (if extracted):"
if [[ -f "$LC_OUTPUT" ]]; then
    echo "   topcat $LC_OUTPUT"
fi
echo ""
echo "4. RUN MORE SCIENCE NIGHTS:"
echo "   # Add more nights to SCIENCE_NIGHTS array and re-run steps 4-7"
echo "   # The template is already built and can be reused"
echo ""
echo "5. ASSESS DIA QUALITY:"
echo "   # Check logs for warnings/errors"
echo "   # Visually inspect difference images"
echo "   # Verify DIA source catalogs are reasonable"
echo ""
echo "================================================================================"
echo ""
