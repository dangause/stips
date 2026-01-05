#!/usr/bin/env bash
#
# batch_ingest_ps1.sh - Batch ingest PS1 templates for multiple fields/bands
#
# This script ingests PS1 templates for a list of coordinates and filter bands,
# useful for preparing templates for a multi-night observing campaign.
#
# Usage:
#   ./scripts/utilities/batch_ingest_ps1.sh \
#       --fields fields.txt \
#       --bands "r,i" \
#       --size 0.2
#
# Fields file format (one per line):
#   NAME RA DEC [TRACT]
#   2023ixf 210.9106 54.3118 1825
#   2020wnt 42.8542 -15.4889 1099
#
# Options:
#   --fields FILE     : File with target coordinates
#   --bands LIST      : Comma-separated list of Nickel bands (b,v,r,i)
#   --size DEGREES    : PS1 cutout size in degrees (default: 0.2)
#   --output-dir DIR  : Directory for FITS files (default: ./ps1_templates)
#   --dry-run         : Print commands without executing
#   -j, --jobs N      : Run N ingestions in parallel (default: 1)

set -euo pipefail

# Get obs_nickel directory
if [[ -z "${OBS_NICKEL:-}" ]]; then
    OBS_NICKEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export OBS_NICKEL
fi

# Source environment
if [[ -f "$OBS_NICKEL/.env" ]]; then
    set -a
    source "$OBS_NICKEL/.env"
    set +a
fi

# Default values
FIELDS_FILE=""
BANDS="r"
CUTOUT_SIZE="0.2"
OUTPUT_DIR="./ps1_templates"
DRY_RUN=false
JOBS=1

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 30 "$0" | grep "^#" | sed 's/^# \?//'
    exit 1
}

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

# ==========================================
# Parse Arguments
# ==========================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fields)
            FIELDS_FILE="${2:-}"
            shift 2
            ;;
        --bands)
            BANDS="${2:-}"
            shift 2
            ;;
        --size)
            CUTOUT_SIZE="${2:-}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -j|--jobs)
            JOBS="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            log_error "Unknown argument: $1"
            usage
            ;;
    esac
done

# ==========================================
# Validate Arguments
# ==========================================

if [[ -z "$FIELDS_FILE" ]]; then
    log_error "Missing required argument: --fields"
    usage
fi

if [[ ! -f "$FIELDS_FILE" ]]; then
    log_error "Fields file not found: $FIELDS_FILE"
    exit 1
fi

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
    log_error "Invalid --jobs value: '$JOBS' (must be positive integer)"
    exit 1
fi

# Validate repository
if [[ -z "${REPO:-}" ]]; then
    log_error "REPO not set. Please set REPO in .env or environment"
    exit 1
fi

if [[ ! -d "$REPO" ]]; then
    log_error "Butler repository not found: $REPO"
    exit 1
fi

# ==========================================
# Setup LSST Stack
# ==========================================

log_info "Setting up LSST Stack..."

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

# ==========================================
# Process Fields
# ==========================================

log_info "========================================="
log_info "Batch PS1 Template Ingestion"
log_info "========================================="
log_info ""
log_info "Fields file:    $FIELDS_FILE"
log_info "Bands:          $BANDS"
log_info "Cutout size:    ${CUTOUT_SIZE}°"
log_info "Output dir:     $OUTPUT_DIR"
log_info "Parallel jobs:  $JOBS"
log_info "Dry run:        $DRY_RUN"
log_info ""

# Parse fields file
FIELD_COUNT=0
TASK_COUNT=0
COMMANDS_FILE=$(mktemp)

while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "${line// }" ]] && continue

    # Parse line: NAME RA DEC [TRACT]
    read -r NAME RA DEC TRACT <<< "$line"

    if [[ -z "$NAME" || -z "$RA" || -z "$DEC" ]]; then
        log_error "Invalid line in fields file: $line"
        continue
    fi

    ((FIELD_COUNT++))

    # Process each band
    IFS=',' read -ra BAND_ARRAY <<< "$BANDS"
    for BAND in "${BAND_ARRAY[@]}"; do
        BAND="${BAND// /}"  # Trim whitespace

        # Validate band
        if [[ ! "$BAND" =~ ^[bvri]$ ]]; then
            log_error "Invalid band: $BAND (must be b, v, r, or i)"
            continue
        fi

        # Build command
        CMD="$OBS_NICKEL/scripts/pipeline/08_ingest_ps1_template.sh \\"
        CMD+=$'\n'"  --ra $RA \\"
        CMD+=$'\n'"  --dec $DEC \\"
        CMD+=$'\n'"  --band $BAND \\"
        CMD+=$'\n'"  --size $CUTOUT_SIZE \\"
        CMD+=$'\n'"  --collection templates/ps1/${NAME}/${BAND} \\"
        CMD+=$'\n'"  --output-dir $OUTPUT_DIR/${NAME}"

        if [[ -n "$TRACT" ]]; then
            CMD+=$'\n'"  --tract $TRACT"
        fi

        ((TASK_COUNT++))

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "Would run:"
            echo "$CMD"
            echo ""
        else
            # Write to commands file for parallel execution
            echo "$CMD" >> "$COMMANDS_FILE"
        fi
    done

done < "$FIELDS_FILE"

log_info "Found $FIELD_COUNT fields, creating $TASK_COUNT ingestion tasks"
log_info ""

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Dry run complete. Use without --dry-run to execute."
    rm -f "$COMMANDS_FILE"
    exit 0
fi

# ==========================================
# Execute Ingestions (Parallel)
# ==========================================

log_info "Starting ingestion (${JOBS} parallel jobs)..."
log_info ""

SUCCESS_COUNT=0
FAIL_COUNT=0
LOG_DIR="$OBS_NICKEL/logs/ps1_batch/$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$LOG_DIR"

# Function to run single ingestion
run_ingestion() {
    local cmd="$1"
    local task_num="$2"
    local log_file="$LOG_DIR/task_${task_num}.log"

    log_info "[Task $task_num] Starting..."

    if eval "$cmd" > "$log_file" 2>&1; then
        log_info "[Task $task_num] SUCCESS"
        return 0
    else
        log_error "[Task $task_num] FAILED (see $log_file)"
        return 1
    fi
}

export -f run_ingestion
export -f log_info
export -f log_error
export LOG_DIR

# Run tasks in parallel using GNU parallel (if available) or xargs
if command -v parallel &> /dev/null; then
    log_info "Using GNU parallel for parallel execution"
    cat "$COMMANDS_FILE" | parallel -j "$JOBS" --line-buffer --tagstring '[Task {#}]' 'bash -c "{}"' \
        && SUCCESS_COUNT=$TASK_COUNT \
        || FAIL_COUNT=$((TASK_COUNT - SUCCESS_COUNT))
else
    log_info "GNU parallel not found, using xargs (less efficient)"

    # Use xargs for parallel execution
    TASK_NUM=0
    while IFS= read -r cmd; do
        ((TASK_NUM++))

        if run_ingestion "$cmd" "$TASK_NUM" & then
            ((SUCCESS_COUNT++))
        else
            ((FAIL_COUNT++))
        fi

        # Limit concurrent jobs
        while [[ $(jobs -r | wc -l) -ge $JOBS ]]; do
            sleep 0.1
        done
    done < "$COMMANDS_FILE"

    # Wait for remaining jobs
    wait
fi

rm -f "$COMMANDS_FILE"

# ==========================================
# Summary
# ==========================================

log_info ""
log_info "========================================="
log_info "Batch Ingestion Complete"
log_info "========================================="
log_info "Total tasks:    $TASK_COUNT"
log_info "Successful:     $SUCCESS_COUNT"
log_info "Failed:         $FAIL_COUNT"
log_info "Logs:           $LOG_DIR"
log_info ""

if [[ $FAIL_COUNT -gt 0 ]]; then
    log_error "Some ingestions failed. Check logs in $LOG_DIR"
    exit 1
fi

log_info "All ingestions completed successfully!"
log_info ""
log_info "Verify templates:"
log_info "  butler query-collections $REPO | grep 'templates/ps1/'"
log_info ""
log_info "Use in DIA:"
log_info "  ./scripts/pipeline/40_diff_imaging.sh --night YYYYMMDD --prefer-ps1 --auto-template"
log_info ""

exit 0
