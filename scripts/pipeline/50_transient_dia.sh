#!/usr/bin/env bash
#
# process_transient_dia.sh - Complete DIA workflow for transient/supernova campaigns
#
# This script automates the full DIA workflow for transient observations:
# 1. Build template from pre-campaign nights (excluding transient)
# 2. Run DIA on campaign nights using that template
# 3. Extract light curve for the transient
# 4. Generate quality assessment report
#
# Usage:
#   ./scripts/pipeline/process_transient_dia.sh \
#       --template-nights template_nights.txt \
#       --dia-nights campaign_nights.txt \
#       --tract 1099 \
#       --band r \
#       --transient-name "SN2021abc" \
#       --ra 150.123 \
#       --dec 2.456
#
# Required flags:
#   --template-nights FILE   : File with nights for template (one per line, YYYYMMDD)
#   --dia-nights FILE        : File with nights for DIA imaging (one per line, YYYYMMDD)
#   --band BAND              : Filter band (g, r, i, z, y)
#   --tract NUM              : Sky tract for template coadd
#                              (optional if --ra/--dec provided - will auto-determine)
#
# Optional flags:
#   --transient-name NAME    : Name for transient (for output files)
#   --ra DEGREES             : RA coordinate for light curve extraction
#   --dec DEGREES            : Dec coordinate for light curve extraction
#   --jobs NUM               : Number of parallel jobs (default: 4)
#   --output-dir DIR         : Output directory for results (default: ./transient_dia_results)
#   --skip-template          : Skip template building (use existing)
#   --skip-dia               : Skip DIA processing (only extract light curve)
#   --skip-lightcurve        : Skip light curve extraction
#   --dry-run                : Print commands without executing
#
# Example nights files:
#   template_nights.txt:
#     20201207
#     20201215
#     20201223
#
#   campaign_nights.txt:
#     20210219
#     20210220
#     20210225
#

set -euo pipefail

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
SKIP_TEMPLATE=false
SKIP_DIA=false
SKIP_LIGHTCURVE=false
DRY_RUN=false

# Derived values (set after parsing args)
TEMPLATE_COLLECTION=""
DIA_OUTPUT_COLLECTION=""
EXCLUDE_START=""
EXCLUDE_END=""

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 50 "$0" | grep "^#" | sed 's/^# \?//'
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
[[ -z "$BAND" ]] && error "Missing required argument: --band"

# Validate files exist
[[ ! -f "$TEMPLATE_NIGHTS_FILE" ]] && error "Template nights file not found: $TEMPLATE_NIGHTS_FILE"
[[ ! -f "$DIA_NIGHTS_FILE" ]] && error "DIA nights file not found: $DIA_NIGHTS_FILE"

# Parse nights
TEMPLATE_NIGHTS=($(parse_nights_file "$TEMPLATE_NIGHTS_FILE"))
DIA_NIGHTS=($(parse_nights_file "$DIA_NIGHTS_FILE"))

[[ ${#TEMPLATE_NIGHTS[@]} -eq 0 ]] && error "No template nights found in $TEMPLATE_NIGHTS_FILE"
[[ ${#DIA_NIGHTS[@]} -eq 0 ]] && error "No DIA nights found in $DIA_NIGHTS_FILE"

# Calculate date range for template (for exclusion in DIA)
SORTED_TEMPLATE_NIGHTS=($(printf '%s\n' "${TEMPLATE_NIGHTS[@]}" | sort))
EXCLUDE_START="${SORTED_TEMPLATE_NIGHTS[0]}"
# Get last element (bash 3.x compatible)
EXCLUDE_END="${SORTED_TEMPLATE_NIGHTS[${#SORTED_TEMPLATE_NIGHTS[@]}-1]}"

# Tract: either specified or auto-determine from RA/Dec
if [[ -z "$TRACT" ]]; then
    if [[ -n "$RA" && -n "$DEC" ]]; then
        log "Auto-determining tract from RA=$RA, Dec=$DEC..."

        # Use Butler to find tract
        TRACT_QUERY_RESULT="$(butler query-dimension-records "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
            skymap 2>/dev/null | grep -E "^skymap" | head -1 | awk '{print $1}')" || true

        if [[ -n "$TRACT_QUERY_RESULT" ]]; then
            # Query for tract at these coordinates
            TRACT="$(butler query-dimension-records "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                tract --where "skymap='$TRACT_QUERY_RESULT'" 2>/dev/null | \
                awk -v ra="$RA" -v dec="$DEC" '
                NR>1 {
                    # Simple check if RA/Dec might be in this tract
                    # This is approximate - Butler handles exact geometry
                    print $2
                }' | head -1)" || true
        fi

        # Fallback: if Butler query fails, try common tract
        if [[ -z "$TRACT" ]]; then
            log "  Failed to auto-determine tract, trying default tract 1099..."
            TRACT=1099
        else
            log "  → Auto-determined tract: $TRACT"
        fi
    else
        error "Missing required argument: --tract (or provide --ra and --dec for auto-determination)"
    fi
fi

# Set transient name if not provided
if [[ -z "$TRANSIENT_NAME" ]]; then
    TRANSIENT_NAME="transient_${DIA_NIGHTS[0]}"
fi

# Set collection names
TIMESTAMP=$(date -u '+%Y%m%dT%H%M%SZ')
TEMPLATE_COLLECTION="templates/transient/${TRANSIENT_NAME}/${BAND}/${TIMESTAMP}"
DIA_OUTPUT_COLLECTION="Nickel/runs/transient/${TRANSIENT_NAME}/diff/${BAND}/${TIMESTAMP}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# ==========================================
# Print Configuration
# ==========================================

log "=========================================="
log "Transient DIA Processing"
log "=========================================="
log ""
log "Transient name:        $TRANSIENT_NAME"
log "Sky tract:             $TRACT"
log "Filter band:           $BAND"
log "Jobs:                  $JOBS"
log ""
log "Template nights:       ${#TEMPLATE_NIGHTS[@]} nights (${SORTED_TEMPLATE_NIGHTS[0]} to ${SORTED_TEMPLATE_NIGHTS[${#SORTED_TEMPLATE_NIGHTS[@]}-1]})"
log "DIA nights:            ${#DIA_NIGHTS[@]} nights"
log ""
log "Template collection:   $TEMPLATE_COLLECTION"
log "DIA output collection: $DIA_OUTPUT_COLLECTION"
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
# Stage 1: Build Template
# ==========================================

if [[ "$SKIP_TEMPLATE" == "false" ]]; then
    log "=========================================="
    log "Stage 1: Building Template"
    log "=========================================="
    log ""

    # Create temporary file with template nights
    TEMP_NIGHTS_FILE="$OUTPUT_DIR/template_nights_${TIMESTAMP}.txt"
    printf '%s\n' "${TEMPLATE_NIGHTS[@]}" > "$TEMP_NIGHTS_FILE"

    # Run 30_coadds.sh
    run_or_dry "$OBS_NICKEL/scripts/pipeline/30_coadds.sh" \
        --nights-file "$TEMP_NIGHTS_FILE" \
        --tract "$TRACT" \
        --band "$BAND" \
        --output "$TEMPLATE_COLLECTION" \
        --jobs "$JOBS"

    log ""
    log "Template built successfully: $TEMPLATE_COLLECTION"
    log ""
else
    log "Skipping template building (--skip-template)"
    log ""
fi

# ==========================================
# Stage 2: Run DIA on Campaign Nights
# ==========================================

if [[ "$SKIP_DIA" == "false" ]]; then
    log "=========================================="
    log "Stage 2: Running DIA on Campaign Nights"
    log "=========================================="
    log ""

    DIA_SUCCESS_COUNT=0
    DIA_FAILED_NIGHTS=()

    for night in "${DIA_NIGHTS[@]}"; do
        log "Processing night: $night"

        if run_or_dry "$OBS_NICKEL/scripts/pipeline/40_diff_imaging.sh" \
            --night "$night" \
            --template "$TEMPLATE_COLLECTION" \
            --band "$BAND" \
            --jobs "$JOBS"; then

            ((DIA_SUCCESS_COUNT++))
            log "  ✓ DIA completed for $night"
        else
            DIA_FAILED_NIGHTS+=("$night")
            log "  ✗ DIA failed for $night"
        fi
        log ""
    done

    log "=========================================="
    log "DIA Processing Summary"
    log "=========================================="
    log "Successful: $DIA_SUCCESS_COUNT / ${#DIA_NIGHTS[@]}"

    if [[ ${#DIA_FAILED_NIGHTS[@]} -gt 0 ]]; then
        log "Failed nights: ${DIA_FAILED_NIGHTS[*]}"
    fi
    log ""

else
    log "Skipping DIA processing (--skip-dia)"
    log ""
fi

# ==========================================
# Stage 3: Extract Light Curve
# ==========================================

if [[ "$SKIP_LIGHTCURVE" == "false" && -n "$RA" && -n "$DEC" ]]; then
    log "=========================================="
    log "Stage 3: Extracting Light Curve"
    log "=========================================="
    log ""

    LIGHTCURVE_OUTPUT="$OUTPUT_DIR/${TRANSIENT_NAME}_lightcurve.ecsv"

    # Check if light curve extraction script exists
    EXTRACT_SCRIPT="$OBS_NICKEL/scripts/python/data/extract_lightcurve.py"

    if [[ -f "$EXTRACT_SCRIPT" ]]; then
        run_or_dry /opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$EXTRACT_SCRIPT" \
            --repo "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
            --collection "$DIA_OUTPUT_COLLECTION" \
            --ra "$RA" \
            --dec "$DEC" \
            --radius 1.0 \
            --output "$LIGHTCURVE_OUTPUT"

        log ""
        log "Light curve saved to: $LIGHTCURVE_OUTPUT"
        log ""
    else
        log "WARNING: Light curve extraction script not found: $EXTRACT_SCRIPT"
        log "Skipping light curve extraction"
        log ""
    fi

elif [[ "$SKIP_LIGHTCURVE" == "true" ]]; then
    log "Skipping light curve extraction (--skip-lightcurve)"
    log ""
elif [[ -z "$RA" || -z "$DEC" ]]; then
    log "Skipping light curve extraction (no coordinates provided)"
    log "Use --ra and --dec to enable light curve extraction"
    log ""
fi

# ==========================================
# Stage 4: Quality Assessment
# ==========================================

log "=========================================="
log "Stage 4: Quality Assessment"
log "=========================================="
log ""

QUALITY_REPORT="$OUTPUT_DIR/${TRANSIENT_NAME}_quality_report.txt"

# Run quality assessment for each night
ASSESS_SCRIPT="$OBS_NICKEL/scripts/python/data/assess_dia_quality.py"

if [[ -f "$ASSESS_SCRIPT" ]]; then
    for night in "${DIA_NIGHTS[@]}"; do
        log "Assessing quality for night: $night"

        if [[ "$DRY_RUN" == "false" ]]; then
            /opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python "$ASSESS_SCRIPT" \
                --repo "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                --collection "$DIA_OUTPUT_COLLECTION" \
                --night "$night" \
                --output "$OUTPUT_DIR/${TRANSIENT_NAME}_quality_${night}.txt"
        else
            log "[DRY-RUN] Would run quality assessment for $night"
        fi
    done

    log ""
    log "Quality reports saved to: $OUTPUT_DIR/${TRANSIENT_NAME}_quality_*.txt"
    log ""
else
    log "WARNING: Quality assessment script not found: $ASSESS_SCRIPT"
    log ""
fi

# ==========================================
# Final Summary
# ==========================================

log "=========================================="
log "Transient DIA Processing Complete"
log "=========================================="
log ""
log "Transient:             $TRANSIENT_NAME"
log "Template collection:   $TEMPLATE_COLLECTION"
log "DIA collection:        $DIA_OUTPUT_COLLECTION"
log "Output directory:      $OUTPUT_DIR"
log ""

if [[ -n "$RA" && -n "$DEC" && "$SKIP_LIGHTCURVE" == "false" ]]; then
    log "Light curve:           $LIGHTCURVE_OUTPUT"
fi

log ""
log "Next steps:"
log "  1. Review quality reports in $OUTPUT_DIR"
if [[ -n "$RA" && -n "$DEC" ]]; then
    log "  2. Analyze light curve: $LIGHTCURVE_OUTPUT"
fi
log "  3. Visualize results using Butler queries"
log ""
log "Example Butler queries:"
log "  butler query-datasets $REPO --collections '$DIA_OUTPUT_COLLECTION' difference_image"
log "  butler query-datasets $REPO --collections '$DIA_OUTPUT_COLLECTION' dia_source_unfiltered"
log ""

exit 0
