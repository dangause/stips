#!/usr/bin/env bash
# 45_forced_photometry.sh - Run forced photometry at catalog positions on science exposures
#
# This script performs forced photometry on calibrated science images (preliminary_visit_image)
# at positions specified in a reference catalog. Useful as a fallback when
# difference imaging fails or for extracting photometry at known positions.
#
# PREREQUISITES:
#   You must source the LSST stack BEFORE running this script:
#     cd /Users/dangause/Developer/lick/lsst/lsst_stack
#     source loadLSST.bash
#     setup lsst_distrib
#     cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel
#
# Usage:
#   ENV_FILE=.env.2020wnt ./45_forced_photometry.sh --night YYYYMMDD [--band BAND]
#
# Examples:
#   # Run forced photometry for all bands on a specific night
#   ENV_FILE=.env.2020wnt ./45_forced_photometry.sh --night 20201207
#
#   # Run for specific band only
#   ENV_FILE=.env.2020wnt ./45_forced_photometry.sh --night 20201207 --band r

# set -eo pipefail  # Don't use -u because of LSST stack env issues

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBS_NICKEL="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Check that LSST stack is loaded by testing pipetask command
if ! command -v pipetask &>/dev/null; then
    echo "ERROR: LSST stack not loaded (pipetask command not found)"
    echo ""
    echo "Please run these commands first:"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack"
    echo "  source loadLSST.bash"
    echo "  setup lsst_distrib"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel"
    echo ""
    echo "Then run this script again."
    exit 1
fi

if ! command -v butler &>/dev/null; then
    echo "ERROR: LSST stack not loaded (butler command not found)"
    echo ""
    echo "Please run these commands first:"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack"
    echo "  source loadLSST.bash"
    echo "  setup lsst_distrib"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# On macOS, ensure DYLD_LIBRARY_PATH is set from LD_LIBRARY_PATH
# The LSST stack sets LD_LIBRARY_PATH but macOS actually needs DYLD_LIBRARY_PATH
if [[ "$OSTYPE" == "darwin"* ]] && [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    if [[ -z "${DYLD_LIBRARY_PATH:-}" ]]; then
        export DYLD_LIBRARY_PATH="$LD_LIBRARY_PATH"
    elif [[ "$DYLD_LIBRARY_PATH" != *"$LD_LIBRARY_PATH"* ]]; then
        export DYLD_LIBRARY_PATH="$LD_LIBRARY_PATH:$DYLD_LIBRARY_PATH"
    fi
fi

# Check if obs_nickel is set up in EUPS
if ! python -c "import lsst.obs.nickel" &>/dev/null; then
    echo "ERROR: obs_nickel package not set up"
    echo ""
    echo "After loading the LSST stack, you also need to setup obs_nickel:"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack"
    echo "  source loadLSST.bash"
    echo "  setup lsst_distrib"
    echo "  setup -r /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel"
    echo "  cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/obs_nickel"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Source utilities
source "$SCRIPT_DIR/../utilities/logging.sh"

# Parse arguments
NIGHT=""
BAND=""
REF_CAT=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --night)
            NIGHT="$2"
            shift 2
            ;;
        --band)
            BAND="$2"
            shift 2
            ;;
        --ref-cat)
            REF_CAT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --night YYYYMMDD [--band BAND] [--ref-cat COLLECTION]"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$NIGHT" ]]; then
    log_error "NIGHT is required (format: YYYYMMDD)"
    exit 1
fi

# Validate night format
if ! [[ "$NIGHT" =~ ^[0-9]{8}$ ]]; then
    log_error "NIGHT must be in YYYYMMDD format, got: $NIGHT"
    exit 1
fi

# Check required environment variables
if [[ -z "${REPO:-}" ]]; then
    log_error "REPO environment variable is not set"
    exit 1
fi

RUN_ID="forced_phot_${NIGHT}_$(date +%Y%m%d_%H%M%S)_$$"
LOG_DIR="$OBS_NICKEL/logs/$RUN_ID/forcedPhot"
mkdir -p "$LOG_DIR"

OUTPUT_COLLECTION="Nickel/runs/${NIGHT}/forcedPhot/${RUN_ID}/run"
# Use processCcd collection (from 20_science.sh output)
INPUT_COLLECTION="Nickel/runs/${NIGHT}/processCcd/*"

log_section "Forced Photometry - Night $NIGHT"
log_info "Repository: $REPO"
log_info "Input collection: $INPUT_COLLECTION"
log_info "Output collection: $OUTPUT_COLLECTION"
log_info "Run ID: $RUN_ID"

if [[ -n "$BAND" ]]; then
    log_info "Band filter: $BAND"
fi

if [[ -n "$REF_CAT" ]]; then
    log_info "Reference catalog: $REF_CAT"
fi

# Build data query
DATA_QUERY="instrument='Nickel' AND exposure.day_obs=${NIGHT}"
if [[ -n "$BAND" ]]; then
    DATA_QUERY="${DATA_QUERY} AND band='${BAND}'"
fi

log_info "Data query: $DATA_QUERY"

# Resolve wildcard collections and check if any exist
log_info "Querying collections..."
RESOLVED_COLLECTIONS=$(butler query-collections "$REPO" "$INPUT_COLLECTION" 2>&1 | tail -n +3 | awk '{print $1}')
log_info "Found collections: $RESOLVED_COLLECTIONS"
if [[ -z "$RESOLVED_COLLECTIONS" ]]; then
    log_error "No input collections found matching: $INPUT_COLLECTION"
    log_error "Make sure science processing (20_science.sh) has been run for night $NIGHT"
    exit 1
fi

# Use the first resolved collection
INPUT_COLLECTION=$(echo "$RESOLVED_COLLECTIONS" | head -1)
log_info "Using input collection: $INPUT_COLLECTION"

# Build pipetask command
PIPETASK_ARGS=(
    pipetask run
    --butler-config "$REPO"
    --input "$INPUT_COLLECTION"
    --output "$OUTPUT_COLLECTION"
    --register-dataset-types
    --pipeline "$OBS_NICKEL/packages/obs_nickel/pipelines/ForcedPhot.yaml"
    --data-query "$DATA_QUERY"
    --output-run "$OUTPUT_COLLECTION"
)

# Add reference catalog if specified
if [[ -n "$REF_CAT" ]]; then
    PIPETASK_ARGS+=(--input "$REF_CAT")
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY RUN] Would execute:"
    echo "  ${PIPETASK_ARGS[*]}"
    exit 0
fi

# Run forced photometry
log_info "Running forced photometry pipeline..."
log_file="$LOG_DIR/pipetask_$(date +%Y%m%dT%H%M%SZ).log"

"${PIPETASK_ARGS[@]}" 2>&1 | tee "$log_file"
EXIT_CODE=${PIPESTATUS[0]}

if [[ $EXIT_CODE -eq 0 ]]; then
    log_info "Forced photometry completed successfully"
    log_info "Output collection: $OUTPUT_COLLECTION"
else
    log_error "Forced photometry failed with exit code $EXIT_CODE"
    log_error "See log: $log_file"
    exit $EXIT_CODE
fi

log_section "Forced Photometry Summary"
log_info "Night: $NIGHT"
log_info "Output collection: $OUTPUT_COLLECTION"
log_info "Logs: $LOG_DIR"
