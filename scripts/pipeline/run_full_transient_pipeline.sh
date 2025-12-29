#!/usr/bin/env bash
#
# run_full_transient_pipeline.sh - Complete end-to-end DIA pipeline for transient campaigns
#
# This script runs the complete LSST Science Pipelines workflow from raw data to DIA analysis:
# 1. Bootstrap repository (if needed)
# 2. Download raw data from archive (optional)
# 3. Build calibrations & ingest raws (10_calibs.sh)
# 4. Run single-frame processing (20_science.sh / processCcd)
# 5. Build template from pre-campaign nights
# 6. Run DIA on campaign nights
# 7. Extract light curve
# 8. Generate quality reports
#
# Usage:
#   ./scripts/pipeline/run_full_transient_pipeline.sh \
#       --template-nights template_nights.txt \
#       --dia-nights campaign_nights.txt \
#       --band r \
#       --tract 1099 \
#       --transient-name "SN2021abc" \
#       --ra 150.123 \
#       --dec 2.456
#
# Required flags:
#   --template-nights FILE   : File with nights for template (one per line, YYYYMMDD)
#   --dia-nights FILE        : File with nights for DIA imaging (one per line, YYYYMMDD)
#   --band BAND              : Filter band (g, r, i, z, y) - if omitted, processes all bands
#
# Optional flags:
#   --tract NUM              : Sky tract (auto-determined from RA/Dec if not provided)
#   --transient-name NAME    : Name for transient (for output files)
#   --ra DEGREES             : RA coordinate for light curve extraction
#   --dec DEGREES            : Dec coordinate for light curve extraction
#   --jobs NUM               : Number of parallel jobs (default: 4)
#   --output-dir DIR         : Output directory for results (default: ./transient_dia_results)
#   --skip-bootstrap         : Skip repository bootstrap (if already done)
#   --skip-download          : Skip raw data download (if already downloaded)
#   --skip-calibs            : Skip calibration building & raw ingest (if already done)
#   --skip-processccd        : Skip single-frame processing (if already done)
#   --skip-template          : Skip template building (use existing)
#   --skip-dia               : Skip DIA processing
#   --skip-lightcurve        : Skip light curve extraction
#   --dry-run                : Print commands without executing
#
# Example:
#   # Full pipeline for SN2020wnt
#   ./scripts/pipeline/run_full_transient_pipeline.sh \
#       --template-nights pre_sn_nights.txt \
#       --dia-nights campaign_nights.txt \
#       --band r \
#       --transient-name "SN2020wnt" \
#       --ra 83.8145 \
#       --dec 3.0847
#
#   # Resume from processCcd (if calibs already done)
#   ./scripts/pipeline/run_full_transient_pipeline.sh \
#       --template-nights pre_sn_nights.txt \
#       --dia-nights campaign_nights.txt \
#       --band r \
#       --transient-name "SN2020wnt" \
#       --ra 83.8145 \
#       --dec 3.0847 \
#       --skip-bootstrap \
#       --skip-download \
#       --skip-calibs
#

# set -euo pipefail

# ==========================================
# Configuration
# ==========================================

# Get obs_nickel directory
if [[ -z "${OBS_NICKEL:-}" ]]; then
    OBS_NICKEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export OBS_NICKEL
fi

# Source common environment
if [[ -f "$OBS_NICKEL/.env" ]]; then
    source "$OBS_NICKEL/.env"
fi

# Default values
TEMPLATE_NIGHTS_FILE=""
DIA_NIGHTS_FILE=""
TRACT=""
BAND=""
TRANSIENT_NAME=""
RA=""
DEC=""
JOBS=4
OUTPUT_DIR="./transient_dia_results"
SKIP_BOOTSTRAP=false
SKIP_DOWNLOAD=false
SKIP_CALIBS=false
SKIP_PROCESSCCD=false
SKIP_TEMPLATE=false
SKIP_DIA=false
SKIP_LIGHTCURVE=false
DRY_RUN=false

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 75 "$0" | grep "^#" | sed 's/^# \?//'
    exit 1
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

run_or_dry() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY-RUN] $*"
    else
        log "Running: $*"
        "$@"
    fi
}

# Parse night list file
parse_nights_file() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        error "Nights file not found: $file"
    fi

    # Read nights, skip empty lines and comments
    grep -v '^#' "$file" | grep -v '^[[:space:]]*$' || true
}

# ==========================================
# Parse Command Line Arguments
# ==========================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --template-nights)
            TEMPLATE_NIGHTS_FILE="${2:-}"
            shift 2
            ;;
        --dia-nights)
            DIA_NIGHTS_FILE="${2:-}"
            shift 2
            ;;
        --tract)
            TRACT="${2:-}"
            shift 2
            ;;
        --band)
            BAND="${2:-}"
            shift 2
            ;;
        --transient-name)
            TRANSIENT_NAME="${2:-}"
            shift 2
            ;;
        --ra)
            RA="${2:-}"
            shift 2
            ;;
        --dec)
            DEC="${2:-}"
            shift 2
            ;;
        --jobs|-j)
            JOBS="${2:-4}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --skip-bootstrap)
            SKIP_BOOTSTRAP=true
            shift
            ;;
        --skip-download)
            SKIP_DOWNLOAD=true
            shift
            ;;
        --skip-calibs)
            SKIP_CALIBS=true
            shift
            ;;
        --skip-processccd)
            SKIP_PROCESSCCD=true
            shift
            ;;
        --skip-template)
            SKIP_TEMPLATE=true
            shift
            ;;
        --skip-dia)
            SKIP_DIA=true
            shift
            ;;
        --skip-lightcurve)
            SKIP_LIGHTCURVE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown argument: $1"
            ;;
    esac
done

# ==========================================
# Validate Arguments
# ==========================================

[[ -z "$TEMPLATE_NIGHTS_FILE" ]] && error "Missing required argument: --template-nights"
[[ -z "$DIA_NIGHTS_FILE" ]] && error "Missing required argument: --dia-nights"

# Validate files exist
[[ ! -f "$TEMPLATE_NIGHTS_FILE" ]] && error "Template nights file not found: $TEMPLATE_NIGHTS_FILE"
[[ ! -f "$DIA_NIGHTS_FILE" ]] && error "DIA nights file not found: $DIA_NIGHTS_FILE"

# Parse nights
TEMPLATE_NIGHTS=($(parse_nights_file "$TEMPLATE_NIGHTS_FILE"))
DIA_NIGHTS=($(parse_nights_file "$DIA_NIGHTS_FILE"))

[[ ${#TEMPLATE_NIGHTS[@]} -eq 0 ]] && error "No template nights found in $TEMPLATE_NIGHTS_FILE"
[[ ${#DIA_NIGHTS[@]} -eq 0 ]] && error "No DIA nights found in $DIA_NIGHTS_FILE"

# Combine all nights for ingest/processCcd
ALL_NIGHTS=($(printf '%s\n' "${TEMPLATE_NIGHTS[@]}" "${DIA_NIGHTS[@]}" | sort -u))

# Set transient name if not provided
if [[ -z "$TRANSIENT_NAME" ]]; then
    TRANSIENT_NAME="transient_${DIA_NIGHTS[0]}"
fi

# Determine bands to process
if [[ -z "$BAND" ]]; then
    # Auto-detect bands from butler registry
    log "No --band specified, detecting available bands from repository..."
    if [[ -n "${BUTLER_REPO:-}" ]]; then
        # Query butler for available bands from processCcd outputs (Nickel: b,v,r,i)
        BANDS=($(butler query-dimension-records "$BUTLER_REPO" band 2>/dev/null | awk 'NF{print $1}' | tr -d ' ' | sort -u || echo ""))
        if [[ ${#BANDS[@]} -eq 0 ]]; then
            # Fallback: check raw data for available bands
            log "Could not query butler, checking raw data for bands..."
            BANDS=(b v r i)  # Default to Nickel filters
        fi
    else
        # No butler repo yet, process all standard bands
        log "No BUTLER_REPO set, defaulting to Nickel bands (b, v, r, i)"
        BANDS=(b v r i)
    fi
    log "Will process bands: ${BANDS[*]}"
else
    # Single band specified
    BANDS=("$BAND")
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# ==========================================
# Print Configuration
# ==========================================

log "=========================================="
log "Full Transient DIA Pipeline"
log "=========================================="
log ""
log "Transient name:        $TRANSIENT_NAME"
log "Filter band(s):        ${BANDS[*]}"
log "Jobs:                  $JOBS"
log ""
log "Template nights:       ${#TEMPLATE_NIGHTS[@]} nights"
log "DIA nights:            ${#DIA_NIGHTS[@]} nights"
log "Total unique nights:   ${#ALL_NIGHTS[@]} nights"
log ""
log "Output directory:      $OUTPUT_DIR"
log ""

if [[ -n "$RA" && -n "$DEC" ]]; then
    log "Light curve coords:    RA=$RA, Dec=$DEC"
    log ""
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log "*** DRY RUN MODE - No commands will be executed ***"
    log ""
fi

# ==========================================
# Stage 0: Bootstrap Repository
# ==========================================

if [[ "$SKIP_BOOTSTRAP" == "false" ]]; then
    log "=========================================="
    log "Stage 0: Bootstrap Repository"
    log "=========================================="
    log ""

    if [[ ! -f "$OBS_NICKEL/scripts/pipeline/00_bootstrap_repo.sh" ]]; then
        error "Bootstrap script not found: $OBS_NICKEL/scripts/pipeline/00_bootstrap_repo.sh"
    fi

    run_or_dry "$OBS_NICKEL/scripts/pipeline/00_bootstrap_repo.sh"

    log ""
    log "Repository bootstrap completed"
    log ""
else
    log "Skipping repository bootstrap (--skip-bootstrap)"
    log ""
fi

# ==========================================
# Stage 1: Download Raw Data
# ==========================================

if [[ "$SKIP_DOWNLOAD" == "false" ]]; then
    log "=========================================="
    log "Stage 1: Download Raw Data"
    log "=========================================="
    log ""

    # Check if download script exists
    DOWNLOAD_SCRIPT="$OBS_NICKEL/scripts/python/pipeline_tools/fetch_archive_night.py"
    if [[ ! -f "$DOWNLOAD_SCRIPT" ]]; then
        log "WARNING: Download script not found: $DOWNLOAD_SCRIPT"
        log "Assuming raw data already downloaded to RAW_PARENT_DIR"
    else
        DOWNLOAD_SUCCESS_COUNT=0
        DOWNLOAD_FAILED_NIGHTS=()

        for night in "${ALL_NIGHTS[@]}"; do
            log "Downloading night: $night"

            DOWNLOAD_ARGS=(--night "$night")
            [[ -n "${LICK_ARCHIVE_DIR:-}" ]] && DOWNLOAD_ARGS+=(--client-path "$LICK_ARCHIVE_DIR")
            [[ -n "${RAW_PARENT_DIR:-}" ]] && DOWNLOAD_ARGS+=(--raw-root "$RAW_PARENT_DIR")

            # Use venv Python if available, otherwise LSST Python
            PYTHON_CMD="/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python"
            if [[ -n "${LICK_ARCHIVE_DIR:-}" && -f "${LICK_ARCHIVE_DIR}/.venv/bin/python" ]]; then
                PYTHON_CMD="${LICK_ARCHIVE_DIR}/.venv/bin/python"
            fi

            if run_or_dry "$PYTHON_CMD" "$DOWNLOAD_SCRIPT" "${DOWNLOAD_ARGS[@]}"; then
                ((DOWNLOAD_SUCCESS_COUNT++))
                log "  ✓ Download completed for $night"
            else
                DOWNLOAD_FAILED_NIGHTS+=("$night")
                log "  ✗ Download failed for $night"
            fi
            log ""
        done

        log "Download Summary: $DOWNLOAD_SUCCESS_COUNT / ${#ALL_NIGHTS[@]} successful"

        if [[ ${#DOWNLOAD_FAILED_NIGHTS[@]} -gt 0 ]]; then
            log "WARNING: Failed nights: ${DOWNLOAD_FAILED_NIGHTS[*]}"
        fi
    fi
    log ""
else
    log "Skipping raw data download (--skip-download)"
    log ""
fi

# ==========================================
# Stage 2: Build Calibrations & Ingest Raws
# ==========================================

if [[ "$SKIP_CALIBS" == "false" ]]; then
    log "=========================================="
    log "Stage 2: Build Calibrations & Ingest Raws"
    log "=========================================="
    log ""

    if [[ ! -f "$OBS_NICKEL/scripts/pipeline/10_calibs.sh" ]]; then
        error "Calibration script not found: $OBS_NICKEL/scripts/pipeline/10_calibs.sh"
    fi

    CALIBS_SUCCESS_COUNT=0
    CALIBS_FAILED_NIGHTS=()

    for night in "${ALL_NIGHTS[@]}"; do
        log "Building calibrations & ingesting raws for night: $night"

        if run_or_dry "$OBS_NICKEL/scripts/pipeline/10_calibs.sh" --night "$night"; then
            ((CALIBS_SUCCESS_COUNT++))
            log "  ✓ Calibrations completed for $night"
        else
            CALIBS_FAILED_NIGHTS+=("$night")
            log "  ✗ Calibrations failed for $night"
        fi
        log ""
    done

    log "Calibrations Summary: $CALIBS_SUCCESS_COUNT / ${#ALL_NIGHTS[@]} successful"

    if [[ ${#CALIBS_FAILED_NIGHTS[@]} -gt 0 ]]; then
        log "WARNING: Failed nights: ${CALIBS_FAILED_NIGHTS[*]}"
    fi
    log ""
else
    log "Skipping calibration building & raw ingest (--skip-calibs)"
    log ""
fi

# ==========================================
# Stage 3: Single-Frame Processing
# ==========================================

if [[ "$SKIP_PROCESSCCD" == "false" ]]; then
    log "=========================================="
    log "Stage 3: Single-Frame Processing (processCcd)"
    log "=========================================="
    log ""

    if [[ ! -f "$OBS_NICKEL/scripts/pipeline/20_science.sh" ]]; then
        error "Science processing script not found: $OBS_NICKEL/scripts/pipeline/20_science.sh"
    fi

    PROCESSCCD_SUCCESS_COUNT=0
    PROCESSCCD_FAILED_NIGHTS=()

    for night in "${ALL_NIGHTS[@]}"; do
        log "Processing night: $night"

        if run_or_dry "$OBS_NICKEL/scripts/pipeline/20_science.sh" --night "$night" --object "$TRANSIENT_NAME" -j "$JOBS" --skip-coadds; then
            ((PROCESSCCD_SUCCESS_COUNT++))
            log "  ✓ ProcessCcd completed for $night"
        else
            PROCESSCCD_FAILED_NIGHTS+=("$night")
            log "  ✗ ProcessCcd failed for $night"
        fi
        log ""
    done

    log "ProcessCcd Summary: $PROCESSCCD_SUCCESS_COUNT / ${#ALL_NIGHTS[@]} successful"

    if [[ ${#PROCESSCCD_FAILED_NIGHTS[@]} -gt 0 ]]; then
        log "WARNING: Failed nights: ${PROCESSCCD_FAILED_NIGHTS[*]}"
    fi
    log ""
else
    log "Skipping single-frame processing (--skip-processccd)"
    log ""
fi

# ==========================================
# Stage 4-7: DIA Workflow
# ==========================================

log "=========================================="
log "Stage 4-7: DIA Workflow"
log "=========================================="
log ""

# Check if 50_transient_dia.sh exists
DIA_SCRIPT="$OBS_NICKEL/scripts/pipeline/50_transient_dia.sh"
if [[ ! -f "$DIA_SCRIPT" ]]; then
    error "DIA workflow script not found: $DIA_SCRIPT"
fi

# Process each band
for CURRENT_BAND in "${BANDS[@]}"; do
    log ""
    log "=========================================="
    log "Processing band: $CURRENT_BAND"
    log "=========================================="

    # Build arguments for DIA script
    DIA_ARGS=(
        --template-nights "$TEMPLATE_NIGHTS_FILE"
        --dia-nights "$DIA_NIGHTS_FILE"
        --band "$CURRENT_BAND"
        --jobs "$JOBS"
        --output-dir "$OUTPUT_DIR"
    )

    [[ -n "$TRACT" ]] && DIA_ARGS+=(--tract "$TRACT")
    [[ -n "$TRANSIENT_NAME" ]] && DIA_ARGS+=(--transient-name "$TRANSIENT_NAME")
    [[ -n "$RA" ]] && DIA_ARGS+=(--ra "$RA")
    [[ -n "$DEC" ]] && DIA_ARGS+=(--dec "$DEC")
    [[ "$SKIP_TEMPLATE" == "true" ]] && DIA_ARGS+=(--skip-template)
    [[ "$SKIP_DIA" == "true" ]] && DIA_ARGS+=(--skip-dia)
    [[ "$SKIP_LIGHTCURVE" == "true" ]] && DIA_ARGS+=(--skip-lightcurve)
    [[ "$DRY_RUN" == "true" ]] && DIA_ARGS+=(--dry-run)

    # Run the DIA workflow for this band
    run_or_dry "$DIA_SCRIPT" "${DIA_ARGS[@]}"

    log "Completed band: $CURRENT_BAND"
done

# ==========================================
# Final Summary
# ==========================================

log ""
log "=========================================="
log "Full Pipeline Complete"
log "=========================================="
log ""
log "Transient:             $TRANSIENT_NAME"
log "Output directory:      $OUTPUT_DIR"
log ""

if [[ "$DRY_RUN" == "false" ]]; then
    log "Next steps:"
    log "  1. Review DIA quality reports in $OUTPUT_DIR"

    if [[ -n "$RA" && -n "$DEC" && "$SKIP_LIGHTCURVE" == "false" ]]; then
        LIGHTCURVE_OUTPUT="$OUTPUT_DIR/${TRANSIENT_NAME}_lightcurve.ecsv"
        if [[ -f "$LIGHTCURVE_OUTPUT" ]]; then
            log "  2. Analyze light curve: $LIGHTCURVE_OUTPUT"
        fi
    fi

    log "  3. Visualize difference images and sources"
    log ""
fi

exit 0
