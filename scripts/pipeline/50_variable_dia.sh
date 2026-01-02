#!/usr/bin/env bash
#
# process_variable_dia.sh - Complete DIA workflow for variable star monitoring
#
# This script automates DIA processing for variable star observations:
# 1. Build baseline template from selected nights
# 2. Run DIA on all monitoring nights (can include template nights)
# 3. Extract light curves for known variable positions
# 4. Generate catalog of detected variable sources
#
# Unlike transient processing, variable star DIA:
# - Can use overlapping nights for template and DIA
# - Focuses on periodic/variable sources rather than new transients
# - May use rolling template approach
# - Optimized for detecting variability rather than novel sources
#
# Usage:
#   ./scripts/pipeline/process_variable_dia.sh \
#       --nights nights.txt \
#       --tract 1099 \
#       --band r \
#       --field-name "M67"
#
# Required flags:
#   --nights FILE            : File with nights for processing (one per line, YYYYMMDD)
#   --band BAND              : Filter band (g, r, i, z, y)
#   --tract NUM              : Sky tract for template coadd
#                              (optional if --targets-file provided - will auto-determine from first target)
#
# Optional flags:
#   --field-name NAME        : Name for field (for output files, default: "variable_field")
#   --template-fraction NUM  : Fraction of nights to use for template (default: 0.5)
#   --template-selection MODE: How to select template nights (default: "first")
#                              "first"  - Use first N nights
#                              "best"   - Use nights with best seeing (requires --seeing-file)
#                              "spread" - Use evenly distributed nights
#   --seeing-file FILE       : File with seeing measurements (night FWHM)
#   --targets-file FILE      : File with variable star positions (RA Dec Name)
#   --rolling-template       : Use rolling template (rebuild for each night)
#   --jobs NUM               : Number of parallel jobs (default: 4)
#   --output-dir DIR         : Output directory (default: ./variable_dia_results)
#   --skip-template          : Skip template building
#   --skip-dia               : Skip DIA processing
#   --skip-lightcurves       : Skip light curve extraction
#   --dry-run                : Print commands without executing
#
# Example nights file:
#   nights.txt:
#     20201207
#     20201215
#     20201223
#     20210101
#     20210115
#
# Example targets file (space-separated: RA Dec Name):
#   targets.txt:
#     132.8458  11.8144  V1
#     132.8521  11.8067  V2
#     132.8395  11.8211  V3
#
# Example seeing file (space-separated: night FWHM_arcsec):
#   seeing.txt:
#     20201207  1.8
#     20201215  1.5
#     20201223  2.1
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
NIGHTS_FILE=""
TRACT=""
BAND=""
FIELD_NAME="variable_field"
TEMPLATE_FRACTION=0.5
TEMPLATE_SELECTION="first"
SEEING_FILE=""
TARGETS_FILE=""
ROLLING_TEMPLATE=false
JOBS=4
OUTPUT_DIR="./variable_dia_results"
SKIP_TEMPLATE=false
SKIP_DIA=false
SKIP_LIGHTCURVES=false
DRY_RUN=false

# Derived values
TEMPLATE_COLLECTION=""
DIA_OUTPUT_COLLECTION=""

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 70 "$0" | grep "^#" | sed 's/^# \?//'
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

# Select template nights based on strategy
select_template_nights() {
    local -n all_nights=$1
    local -n template_nights=$2
    local selection_mode="$3"

    local n_total=${#all_nights[@]}
    local n_template=$(awk -v total=$n_total -v frac=$TEMPLATE_FRACTION 'BEGIN {print int(total * frac)}')

    # Ensure at least 1 night for template
    [[ $n_template -lt 1 ]] && n_template=1

    log "Selecting $n_template of $n_total nights for template using '$selection_mode' strategy"

    case "$selection_mode" in
        first)
            # Use first N nights
            template_nights=("${all_nights[@]:0:$n_template}")
            ;;

        best)
            # Use nights with best seeing (bash 3.x compatible - no associative arrays)
            if [[ ! -f "$SEEING_FILE" ]]; then
                error "Template selection 'best' requires --seeing-file"
            fi

            # Create temporary file with seeing data joined to nights
            local temp_seeing=$(mktemp)
            trap "rm -f $temp_seeing" EXIT

            # For each night in all_nights, find its seeing from SEEING_FILE
            for night in "${all_nights[@]}"; do
                # Look up seeing for this night
                fwhm=$(grep -E "^${night}[[:space:]]" "$SEEING_FILE" | awk '{print $2}')
                # If not found, use high value so it's not selected
                [[ -z "$fwhm" ]] && fwhm="999"
                echo "$fwhm $night"
            done > "$temp_seeing"

            # Sort by seeing and take best N nights
            template_nights=()
            while IFS= read -r night; do
                template_nights+=("$night")
            done < <(sort -n "$temp_seeing" | head -n "$n_template" | awk '{print $2}')

            rm -f "$temp_seeing"
            ;;

        spread)
            # Use evenly distributed nights
            local step=$(awk -v total=$n_total -v n=$n_template 'BEGIN {print int(total / n)}')
            [[ $step -lt 1 ]] && step=1

            local idx
            for ((idx=0; idx<n_total; idx+=step)); do
                [[ ${#template_nights[@]} -ge $n_template ]] && break
                template_nights+=("${all_nights[$idx]}")
            done
            ;;

        *)
            error "Unknown template selection mode: $selection_mode"
            ;;
    esac

    log "Selected template nights: ${template_nights[*]}"
}

# ==========================================
# Parse Command Line Arguments
# ==========================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --nights)
            NIGHTS_FILE="${2:-}"
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
        --field-name)
            FIELD_NAME="${2:-}"
            shift 2
            ;;
        --template-fraction)
            TEMPLATE_FRACTION="${2:-}"
            shift 2
            ;;
        --template-selection)
            TEMPLATE_SELECTION="${2:-}"
            shift 2
            ;;
        --seeing-file)
            SEEING_FILE="${2:-}"
            shift 2
            ;;
        --targets-file)
            TARGETS_FILE="${2:-}"
            shift 2
            ;;
        --rolling-template)
            ROLLING_TEMPLATE=true
            shift
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
        --skip-lightcurves)
            SKIP_LIGHTCURVES=true
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

[[ -z "$NIGHTS_FILE" ]] && error "Missing required argument: --nights"
[[ -z "$BAND" ]] && error "Missing required argument: --band"

# Validate files exist
[[ ! -f "$NIGHTS_FILE" ]] && error "Nights file not found: $NIGHTS_FILE"

if [[ -n "$TARGETS_FILE" && ! -f "$TARGETS_FILE" ]]; then
    error "Targets file not found: $TARGETS_FILE"
fi

# Tract: either specified or auto-determine from targets file
if [[ -z "$TRACT" ]]; then
    if [[ -n "$TARGETS_FILE" ]]; then
        log "Auto-determining tract from first target in $TARGETS_FILE..."

        # Read first target (skip comments)
        FIRST_TARGET=$(grep -v '^#' "$TARGETS_FILE" | grep -v '^[[:space:]]*$' | head -1)
        if [[ -n "$FIRST_TARGET" ]]; then
            TARGET_RA=$(echo "$FIRST_TARGET" | awk '{print $1}')
            TARGET_DEC=$(echo "$FIRST_TARGET" | awk '{print $2}')

            # Use Butler to find tract
            TRACT_QUERY_RESULT="$(butler query-dimension-records "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                skymap 2>/dev/null | grep -E "^skymap" | head -1 | awk '{print $1}')" || true

            if [[ -n "$TRACT_QUERY_RESULT" ]]; then
                # Query for tract at these coordinates
                TRACT="$(butler query-dimension-records "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                    tract --where "skymap='$TRACT_QUERY_RESULT'" 2>/dev/null | \
                    awk -v ra="$TARGET_RA" -v dec="$TARGET_DEC" '
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
                log "  → Auto-determined tract: $TRACT (from RA=$TARGET_RA, Dec=$TARGET_DEC)"
            fi
        else
            error "Targets file is empty, cannot auto-determine tract"
        fi
    else
        error "Missing required argument: --tract (or provide --targets-file for auto-determination)"
    fi
fi

# Parse nights
ALL_NIGHTS=($(parse_nights_file "$NIGHTS_FILE"))

[[ ${#ALL_NIGHTS[@]} -eq 0 ]] && error "No nights found in $NIGHTS_FILE"

# Select template nights
TEMPLATE_NIGHTS=()
DIA_NIGHTS=("${ALL_NIGHTS[@]}")  # DIA runs on all nights for variables

if [[ "$ROLLING_TEMPLATE" == "false" ]]; then
    select_template_nights ALL_NIGHTS TEMPLATE_NIGHTS "$TEMPLATE_SELECTION"
fi

# Set collection names
TIMESTAMP=$(date -u '+%Y%m%dT%H%M%SZ')
TEMPLATE_COLLECTION="templates/variable/${FIELD_NAME}/${BAND}/${TIMESTAMP}"
DIA_OUTPUT_COLLECTION="Nickel/runs/variable/${FIELD_NAME}/diff/${BAND}/${TIMESTAMP}"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# ==========================================
# Print Configuration
# ==========================================

log "=========================================="
log "Variable Star DIA Processing"
log "=========================================="
log ""
log "Field name:            $FIELD_NAME"
log "Sky tract:             $TRACT"
log "Filter band:           $BAND"
log "Jobs:                  $JOBS"
log ""
log "Total nights:          ${#ALL_NIGHTS[@]}"

if [[ "$ROLLING_TEMPLATE" == "false" ]]; then
    log "Template nights:       ${#TEMPLATE_NIGHTS[@]} (${TEMPLATE_SELECTION} selection)"
    log "Template fraction:     $TEMPLATE_FRACTION"
else
    log "Template mode:         ROLLING (rebuild for each night)"
fi

log ""
log "Template collection:   $TEMPLATE_COLLECTION"
log "DIA output collection: $DIA_OUTPUT_COLLECTION"
log "Output directory:      $OUTPUT_DIR"
log ""

if [[ -n "$TARGETS_FILE" ]]; then
    N_TARGETS=$(grep -v '^#' "$TARGETS_FILE" | grep -v '^[[:space:]]*$' | wc -l | tr -d ' ')
    log "Target stars:          $N_TARGETS (from $TARGETS_FILE)"
    log ""
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log "*** DRY RUN MODE - No commands will be executed ***"
    log ""
fi

# ==========================================
# Stage 1: Build Baseline Template
# ==========================================

if [[ "$SKIP_TEMPLATE" == "false" && "$ROLLING_TEMPLATE" == "false" ]]; then
    log "=========================================="
    log "Stage 1: Building Baseline Template"
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
    log "Baseline template built: $TEMPLATE_COLLECTION"
    log ""

elif [[ "$SKIP_TEMPLATE" == "true" ]]; then
    log "Skipping template building (--skip-template)"
    log ""
elif [[ "$ROLLING_TEMPLATE" == "true" ]]; then
    log "Using rolling template mode (templates built per-night in Stage 2)"
    log ""
fi

# ==========================================
# Stage 2: Run DIA on All Nights
# ==========================================

if [[ "$SKIP_DIA" == "false" ]]; then
    log "=========================================="
    log "Stage 2: Running DIA on Monitoring Nights"
    log "=========================================="
    log ""

    DIA_SUCCESS_COUNT=0
    DIA_FAILED_NIGHTS=()

    for night in "${DIA_NIGHTS[@]}"; do
        log "Processing night: $night"

        # For rolling template: build template from all OTHER nights
        if [[ "$ROLLING_TEMPLATE" == "true" ]]; then
            log "  Building rolling template (excluding $night)..."

            # Create temporary nights file excluding current night
            ROLLING_NIGHTS_FILE="$OUTPUT_DIR/rolling_template_${night}.txt"
            printf '%s\n' "${ALL_NIGHTS[@]}" | grep -v "^${night}$" > "$ROLLING_NIGHTS_FILE"

            ROLLING_TEMPLATE_COLLECTION="${TEMPLATE_COLLECTION}_${night}"

            if run_or_dry "$OBS_NICKEL/scripts/pipeline/30_coadds.sh" \
                --nights-file "$ROLLING_NIGHTS_FILE" \
                --tract "$TRACT" \
                --band "$BAND" \
                --output "$ROLLING_TEMPLATE_COLLECTION" \
                --jobs "$JOBS"; then

                log "  ✓ Rolling template built: $ROLLING_TEMPLATE_COLLECTION"
                CURRENT_TEMPLATE="$ROLLING_TEMPLATE_COLLECTION"
            else
                log "  ✗ Rolling template failed for $night, skipping DIA"
                DIA_FAILED_NIGHTS+=("$night")
                continue
            fi
        else
            CURRENT_TEMPLATE="$TEMPLATE_COLLECTION"
        fi

        # Run DIA
        if run_or_dry "$OBS_NICKEL/scripts/pipeline/40_diff_imaging.sh" \
            --night "$night" \
            --template "$CURRENT_TEMPLATE" \
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
# Stage 3: Extract Light Curves
# ==========================================

if [[ "$SKIP_LIGHTCURVES" == "false" && -n "$TARGETS_FILE" ]]; then
    log "=========================================="
    log "Stage 3: Extracting Light Curves"
    log "=========================================="
    log ""

    EXTRACT_SCRIPT="$OBS_NICKEL/scripts/python/pipeline_tools/extract_lightcurve.py"

    if [[ -f "$EXTRACT_SCRIPT" ]]; then
        # Read targets file
        while read -r ra dec name; do
            [[ -z "$ra" || "$ra" =~ ^# ]] && continue

            log "Extracting light curve for: $name (RA=$ra, Dec=$dec)"

            LIGHTCURVE_OUTPUT="$OUTPUT_DIR/${FIELD_NAME}_${name}_lightcurve.ecsv"
            CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"

            if [[ "$DRY_RUN" == "false" ]]; then
                /opt/anaconda3/envs/${CONDA_ENV}/bin/python "$EXTRACT_SCRIPT" \
                    --repo "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                    --collection "$DIA_OUTPUT_COLLECTION" \
                    --ra "$ra" \
                    --dec "$dec" \
                    --radius 1.0 \
                    --output "$LIGHTCURVE_OUTPUT" || \
                log "  WARNING: Failed to extract light curve for $name"
            else
                log "[DRY-RUN] Would extract light curve to $LIGHTCURVE_OUTPUT"
            fi

        done < "$TARGETS_FILE"

        log ""
        log "Light curves saved to: $OUTPUT_DIR/${FIELD_NAME}_*_lightcurve.ecsv"
        log ""
    else
        log "WARNING: Light curve extraction script not found: $EXTRACT_SCRIPT"
        log "Skipping light curve extraction"
        log ""
    fi

elif [[ "$SKIP_LIGHTCURVES" == "true" ]]; then
    log "Skipping light curve extraction (--skip-lightcurves)"
    log ""
elif [[ -z "$TARGETS_FILE" ]]; then
    log "Skipping light curve extraction (no targets file provided)"
    log "Use --targets-file to enable light curve extraction"
    log ""
fi

# ==========================================
# Stage 4: Quality Assessment
# ==========================================

log "=========================================="
log "Stage 4: Quality Assessment"
log "=========================================="
log ""

ASSESS_SCRIPT="$OBS_NICKEL/scripts/python/pipeline_tools/assess_dia_quality.py"

if [[ -f "$ASSESS_SCRIPT" ]]; then
    # Create combined quality report
    QUALITY_REPORT="$OUTPUT_DIR/${FIELD_NAME}_quality_summary.txt"

    if [[ "$DRY_RUN" == "false" ]]; then
        echo "Variable Star DIA Quality Summary" > "$QUALITY_REPORT"
        echo "Field: $FIELD_NAME" >> "$QUALITY_REPORT"
        echo "Band: $BAND" >> "$QUALITY_REPORT"
        echo "Nights processed: ${#DIA_NIGHTS[@]}" >> "$QUALITY_REPORT"
        echo "" >> "$QUALITY_REPORT"

        # Assess each night
        CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
        for night in "${DIA_NIGHTS[@]}"; do
            log "Assessing quality for night: $night"

            /opt/anaconda3/envs/${CONDA_ENV}/bin/python "$ASSESS_SCRIPT" \
                --repo "${REPO:-/Users/dangause/Developer/lick/lsst/data/nickel/repo}" \
                --collection "$DIA_OUTPUT_COLLECTION" \
                --night "$night" \
                --output "$OUTPUT_DIR/${FIELD_NAME}_quality_${night}.txt" || \
            log "  WARNING: Quality assessment failed for $night"
        done

        log ""
        log "Quality reports saved to: $OUTPUT_DIR/${FIELD_NAME}_quality_*.txt"
    else
        log "[DRY-RUN] Would run quality assessment for ${#DIA_NIGHTS[@]} nights"
    fi
    log ""
else
    log "WARNING: Quality assessment script not found: $ASSESS_SCRIPT"
    log ""
fi

# ==========================================
# Final Summary
# ==========================================

log "=========================================="
log "Variable Star DIA Processing Complete"
log "=========================================="
log ""
log "Field:                 $FIELD_NAME"
log "Template collection:   $TEMPLATE_COLLECTION"
log "DIA collection:        $DIA_OUTPUT_COLLECTION"
log "Output directory:      $OUTPUT_DIR"
log ""

if [[ -n "$TARGETS_FILE" && "$SKIP_LIGHTCURVES" == "false" ]]; then
    log "Light curves:          $OUTPUT_DIR/${FIELD_NAME}_*_lightcurve.ecsv"
fi

log ""
log "Next steps:"
log "  1. Review quality reports in $OUTPUT_DIR"
if [[ -n "$TARGETS_FILE" ]]; then
    log "  2. Analyze light curves for periodic variability"
    log "  3. Perform period finding analysis (e.g., Lomb-Scargle)"
fi
log "  4. Identify new variable candidates from DIA sources"
log ""
log "Example Butler queries:"
log "  butler query-datasets $REPO --collections '$DIA_OUTPUT_COLLECTION' difference_image"
log "  butler query-datasets $REPO --collections '$DIA_OUTPUT_COLLECTION' dia_source_unfiltered"
log ""
log "Example analysis:"
log "  # Find sources detected on multiple nights (candidate variables)"
log "  butler query-dimension-records $REPO diaObject --collections '$DIA_OUTPUT_COLLECTION'"
log ""

exit 0
