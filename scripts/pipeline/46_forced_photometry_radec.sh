#!/usr/bin/env bash
# 46_forced_photometry_radec.sh - Forced photometry at specified RA/Dec coordinates
#
# Performs forced photometry at arbitrary sky positions on:
#   - Calibrated visit images (preliminary_visit_image)
#   - Difference images (difference_image)
#
# PREREQUISITES:
#   You must source the LSST stack BEFORE running this script:
#     cd /Users/dangause/Developer/lick/lsst/lsst_stack
#     source loadLSST.bash
#     setup lsst_distrib
#     cd /path/to/nickel_processing_suite
#
# Usage:
#   ./46_forced_photometry_radec.sh --night YYYYMMDD --ra RA --dec DEC [options]
#   ./46_forced_photometry_radec.sh --night YYYYMMDD --coords-file FILE [options]
#
# Options:
#   --night YYYYMMDD      Night to process (required)
#   --ra RA               RA in degrees (can specify multiple times)
#   --dec DEC             Dec in degrees (must match number of --ra)
#   --coords-file FILE    CSV/FITS file with ra,dec columns (alternative to --ra/--dec)
#   --band BAND           Filter band to process (optional, default: all)
#   --image-type TYPE     Image type: 'visit', 'diffim', or 'both' (default: both)
#   --run-id ID           Override output run identifier (optional)
#   --dry-run             Show what would be run without executing
#
# Examples:
#   # Single target on all images:
#   ./46_forced_photometry_radec.sh --night 20201207 --ra 185.7285 --dec 15.8225
#
#   # Multiple targets:
#   ./46_forced_photometry_radec.sh --night 20201207 \
#       --ra 185.7285 --dec 15.8225 \
#       --ra 186.1234 --dec 16.5678
#
#   # From coordinate file:
#   ./46_forced_photometry_radec.sh --night 20201207 --coords-file targets.csv
#
#   # Difference images only:
#   ./46_forced_photometry_radec.sh --night 20201207 --ra 185.7285 --dec 15.8225 --image-type diffim

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OBS_NICKEL="$REPO_ROOT/packages/obs_nickel"

# Ensure obs_nickel is in PYTHONPATH for pipetask subprocess
export PYTHONPATH="${OBS_NICKEL}/python:${REPO_ROOT}/packages/obs_nickel_data/python:${PYTHONPATH:-}"

# Preserve REPO if already set (e.g., from parent script)
_INHERITED_REPO="${REPO:-}"

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Restore inherited REPO if it was set (parent script takes precedence)
if [[ -n "$_INHERITED_REPO" ]]; then
    REPO="$_INHERITED_REPO"
fi

# Check that LSST stack is loaded
if ! command -v pipetask &>/dev/null; then
    echo "ERROR: LSST stack not loaded (pipetask command not found)"
    echo ""
    echo "Please run these commands first:"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack"
    echo "  source loadLSST.bash"
    echo "  setup lsst_distrib"
    echo "  cd $REPO_ROOT"
    exit 1
fi

if ! command -v butler &>/dev/null; then
    echo "ERROR: LSST stack not loaded (butler command not found)"
    exit 1
fi

# On macOS, ensure DYLD_LIBRARY_PATH is set
if [[ "$OSTYPE" == "darwin"* ]] && [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    if [[ -z "${DYLD_LIBRARY_PATH:-}" ]]; then
        export DYLD_LIBRARY_PATH="$LD_LIBRARY_PATH"
    elif [[ "$DYLD_LIBRARY_PATH" != *"$LD_LIBRARY_PATH"* ]]; then
        export DYLD_LIBRARY_PATH="$LD_LIBRARY_PATH:$DYLD_LIBRARY_PATH"
    fi
fi

# Note: obs_nickel PYTHONPATH is set above to ensure pipetask can import lsst.obs.nickel

# Source utilities
source "$SCRIPT_DIR/../utilities/logging.sh"

# Parse arguments
NIGHT=""
BAND=""
IMAGE_TYPE="both"
DRY_RUN=false
COORDS_FILE=""
RUN_ID_OVERRIDE=""
declare -a RA_LIST
declare -a DEC_LIST

while [[ $# -gt 0 ]]; do
    case $1 in
        --night)
            NIGHT="$2"
            shift 2
            ;;
        --ra)
            RA_LIST+=("$2")
            shift 2
            ;;
        --dec)
            DEC_LIST+=("$2")
            shift 2
            ;;
        --coords-file)
            COORDS_FILE="$2"
            shift 2
            ;;
        --band)
            BAND="$2"
            shift 2
            ;;
        --image-type)
            IMAGE_TYPE="$2"
            shift 2
            ;;
        --run-id)
            RUN_ID_OVERRIDE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            head -50 "$0" | tail -n +2
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --night YYYYMMDD --ra RA --dec DEC [options]"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$NIGHT" ]]; then
    log_error "NIGHT is required (format: YYYYMMDD)"
    exit 1
fi

if ! [[ "$NIGHT" =~ ^[0-9]{8}$ ]]; then
    log_error "NIGHT must be in YYYYMMDD format, got: $NIGHT"
    exit 1
fi

# Check we have coordinates
if [[ -z "$COORDS_FILE" ]] && [[ ${#RA_LIST[@]} -eq 0 ]]; then
    log_error "Must specify either --ra/--dec or --coords-file"
    exit 1
fi

if [[ ${#RA_LIST[@]} -ne ${#DEC_LIST[@]} ]]; then
    log_error "Number of --ra and --dec arguments must match"
    exit 1
fi

# Validate image type
case "$IMAGE_TYPE" in
    visit|diffim|both) ;;
    *)
        log_error "Invalid --image-type: $IMAGE_TYPE (must be 'visit', 'diffim', or 'both')"
        exit 1
        ;;
esac

if [[ -z "${REPO:-}" ]]; then
    log_error "REPO environment variable is not set"
    exit 1
fi

RUN_ID="${RUN_ID_OVERRIDE:-forced_phot_radec_${NIGHT}_$(date +%Y%m%d_%H%M%S)_$$}"
LOG_DIR="$REPO_ROOT/logs/$RUN_ID"
mkdir -p "$LOG_DIR"

log_section "Forced Photometry at RA/Dec - Night $NIGHT"
log_info "Repository: $REPO"
log_info "Run ID: $RUN_ID"
log_info "Image type: $IMAGE_TYPE"

# Build coordinate config arguments
if [[ -n "$COORDS_FILE" ]]; then
    log_info "Coordinate file: $COORDS_FILE"
    # TODO: Register coordinate file as Butler dataset
    # For now, we'll parse it and use config coords
    if [[ ! -f "$COORDS_FILE" ]]; then
        log_error "Coordinate file not found: $COORDS_FILE"
        exit 1
    fi

    # Parse CSV file (assumes header: id,ra,dec or ra,dec)
    log_info "Parsing coordinate file..."
    while IFS=, read -r col1 col2 col3; do
        # Skip header
        if [[ "$col1" == "id" ]] || [[ "$col1" == "ra" ]]; then
            continue
        fi
        # Handle both id,ra,dec and ra,dec formats
        if [[ -n "$col3" ]]; then
            RA_LIST+=("$col2")
            DEC_LIST+=("$col3")
        else
            RA_LIST+=("$col1")
            DEC_LIST+=("$col2")
        fi
    done < "$COORDS_FILE"
fi

log_info "Number of coordinates: ${#RA_LIST[@]}"
for i in "${!RA_LIST[@]}"; do
    log_info "  Target $((i+1)): RA=${RA_LIST[$i]}, Dec=${DEC_LIST[$i]}"
done

# Build RA/Dec config strings
RA_CONFIG="["
DEC_CONFIG="["
for i in "${!RA_LIST[@]}"; do
    if [[ $i -gt 0 ]]; then
        RA_CONFIG+=","
        DEC_CONFIG+=","
    fi
    RA_CONFIG+="${RA_LIST[$i]}"
    DEC_CONFIG+="${DEC_LIST[$i]}"
done
RA_CONFIG+="]"
DEC_CONFIG+="]"

# Build data query - just instrument, let the collection constrain the data
DATA_QUERY="instrument='Nickel'"
if [[ -n "$BAND" ]]; then
    DATA_QUERY="${DATA_QUERY} AND band='${BAND}'"
    log_info "Band filter: $BAND"
fi
log_info "Data query: $DATA_QUERY"

# Find input collections
PROCESSCCD_COLLECTION="Nickel/runs/${NIGHT}/processCcd/*"
DIFF_COLLECTION="Nickel/runs/${NIGHT}/diff/*"

# Resolve processCcd collection - look for the /run subcollection
log_info "Looking for processCcd collections..."
PROCESSCCD_RUN_COLLECTION="Nickel/runs/${NIGHT}/processCcd/*/run"
RESOLVED_PROCESSCCD=$(butler query-collections "$REPO" "$PROCESSCCD_RUN_COLLECTION" 2>&1 | tail -n +3 | awk '{print $1}' | sort | tail -1)
if [[ -z "$RESOLVED_PROCESSCCD" ]]; then
    # Try without /run suffix as fallback
    RESOLVED_PROCESSCCD=$(butler query-collections "$REPO" "$PROCESSCCD_COLLECTION" 2>&1 | tail -n +3 | awk '{print $1}' | sort | tail -1)
fi
if [[ -z "$RESOLVED_PROCESSCCD" ]]; then
    log_error "No processCcd collections found for night $NIGHT"
    log_error "Run 20_science.sh first"
    exit 1
fi
log_info "Using processCcd collection: $RESOLVED_PROCESSCCD"

# Function to run forced photometry pipeline
run_forced_phot() {
    local pipeline_subset="$1"
    local output_suffix="$2"
    local input_collections="$3"
    local task_name="$4"

    # Include band in output collection path to avoid conflicts when running multiple bands
    local band_suffix=""
    if [[ -n "$BAND" ]]; then
        band_suffix="_${BAND}"
    fi
    local OUTPUT_COLLECTION="Nickel/runs/${NIGHT}/forcedPhotRaDec/${RUN_ID}/${output_suffix}${band_suffix}"
    local OUTPUT_RUN="${OUTPUT_COLLECTION}/run"

    log_info "Running $pipeline_subset..."
    log_info "  Input: $input_collections"
    log_info "  Output: $OUTPUT_COLLECTION"
    log_info "  Output run: $OUTPUT_RUN"

    local PIPETASK_ARGS=(
        pipetask run
        --butler-config "$REPO"
        --input "$input_collections"
        --output "$OUTPUT_COLLECTION"
        --register-dataset-types
        --pipeline "$OBS_NICKEL/pipelines/ForcedPhotRaDec.yaml#${pipeline_subset}"
        --data-query "$DATA_QUERY"
        --output-run "$OUTPUT_RUN"
        -c "${task_name}:useConfigCoords=True"
        -c "${task_name}:ra=${RA_CONFIG}"
        -c "${task_name}:dec=${DEC_CONFIG}"
    )

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would execute:"
        echo "  ${PIPETASK_ARGS[*]}"
        return 0
    fi

    local log_file="$LOG_DIR/${output_suffix}_$(date +%Y%m%dT%H%M%SZ).log"
    "${PIPETASK_ARGS[@]}" 2>&1 | tee "$log_file"
    local EXIT_CODE=${PIPESTATUS[0]}

    if [[ $EXIT_CODE -eq 0 ]]; then
        log_info "$pipeline_subset completed successfully"
        log_info "Output: $OUTPUT_COLLECTION"
    else
        log_error "$pipeline_subset failed with exit code $EXIT_CODE"
        log_error "See log: $log_file"
    fi

    return $EXIT_CODE
}

# Run forced photometry based on image type
EXIT_CODE=0

if [[ "$IMAGE_TYPE" == "visit" ]] || [[ "$IMAGE_TYPE" == "both" ]]; then
    run_forced_phot "visit-image" "visit" "$RESOLVED_PROCESSCCD" "forcedPhotRaDec"
    EXIT_CODE=$?
fi

if [[ "$IMAGE_TYPE" == "diffim" ]] || [[ "$IMAGE_TYPE" == "both" ]]; then
    # Check for difference image collection
    # Use only the latest diff collection to avoid duplicate data from previous runs
    log_info "Looking for diff collections..."
    RESOLVED_DIFF=$(butler query-collections "$REPO" "$DIFF_COLLECTION" 2>&1 | tail -n +3 | awk '{print $1}' | grep -E '/run$' | sort | tail -1)

    if [[ -z "$RESOLVED_DIFF" ]]; then
        log_warning "No diff collections found for night $NIGHT"
        log_warning "Skipping difference image forced photometry"
        log_warning "Run 40_diff_imaging.sh first to create difference images"
    else
        log_info "Using diff collection: $RESOLVED_DIFF"
        INPUT_COLLECTIONS="${RESOLVED_PROCESSCCD},${RESOLVED_DIFF}"
        run_forced_phot "diffim" "diffim" "$INPUT_COLLECTIONS" "forcedPhotDiffimRaDec"
        DIFF_EXIT=$?
        if [[ $DIFF_EXIT -ne 0 ]]; then
            EXIT_CODE=$DIFF_EXIT
        fi
    fi
fi

log_section "Forced Photometry Summary"
log_info "Night: $NIGHT"
log_info "Coordinates: ${#RA_LIST[@]} targets"
log_info "Image types: $IMAGE_TYPE"
log_info "Logs: $LOG_DIR"

if [[ $EXIT_CODE -eq 0 ]]; then
    log_info "All forced photometry completed successfully"
else
    log_error "Some forced photometry tasks failed"
fi

exit $EXIT_CODE
