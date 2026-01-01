#!/usr/bin/env bash
#
# 08_ingest_ps1_template.sh - Download and ingest PS1 templates for DIA
#
# This script wraps the Python PS1 template ingestion tool for easy use
# in the Nickel pipeline workflow.
#
# Usage:
#   ./scripts/pipeline/08_ingest_ps1_template.sh \
#       --ra 150.123 \
#       --dec 2.456 \
#       --band r \
#       --collection templates/ps1/r
#
# Required flags:
#   --ra DEGREES          : Right ascension in degrees
#   --dec DEGREES         : Declination in degrees
#   --band BAND           : Nickel band (b, v, r, i)
#
# Optional flags:
#   --collection NAME     : Output collection (default: templates/ps1/{band})
#   --tract NUM           : Sky tract (auto-determined if not provided)
#   --ps1-band BAND       : PS1 band to download (default: auto-mapped)
#   --size DEGREES        : Cutout size in degrees (default: 0.2)
#   --output-dir DIR      : Directory for FITS files (default: ./ps1_templates)
#   --ps1-fits FILE       : Use existing PS1 FITS file
#   --skip-download       : Skip download (use with --ps1-fits)
#   --skip-ingest         : Download only, don't ingest
#   -v, --verbose         : Verbose output
#


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
RA=""
DEC=""
BAND=""
COLLECTION=""
TRACT=""
PS1_BAND=""
CUTOUT_SIZE="0.2"
OUTPUT_DIR="./ps1_templates"
PS1_FITS=""
SKIP_DOWNLOAD=false
SKIP_INGEST=false
VERBOSE=false

# ==========================================
# Setup Logging
# ==========================================

# Source logging utilities if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/../utilities/logging.sh" ]]; then
    source "$SCRIPT_DIR/../utilities/logging.sh"
else
    # Fallback logging functions if logging.sh not available
    log_info() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"; }
    log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }
    log_warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"; }
    log_section() { echo ""; echo "========================================"; echo "  $*"; echo "========================================"; }
fi

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 30 "$0" | grep "^#" | sed 's/^# \?//'
    exit 1
}

error() {
    log_error "$*"
    exit 1
}

# ==========================================
# Parse Arguments
# ==========================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ra)
            RA="${2:-}"
            shift 2
            ;;
        --dec)
            DEC="${2:-}"
            shift 2
            ;;
        --band)
            BAND="${2:-}"
            shift 2
            ;;
        --collection)
            COLLECTION="${2:-}"
            shift 2
            ;;
        --tract)
            TRACT="${2:-}"
            shift 2
            ;;
        --ps1-band)
            PS1_BAND="${2:-}"
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
        --ps1-fits)
            PS1_FITS="${2:-}"
            shift 2
            ;;
        --skip-download)
            SKIP_DOWNLOAD=true
            shift
            ;;
        --skip-ingest)
            SKIP_INGEST=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
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

[[ -z "$RA" ]] && error "Missing required argument: --ra"
[[ -z "$DEC" ]] && error "Missing required argument: --dec"
[[ -z "$BAND" ]] && error "Missing required argument: --band"

# Validate band
if [[ ! "$BAND" =~ ^[bvri]$ ]]; then
    error "Invalid band: $BAND (must be b, v, r, or i)"
fi

# Set default collection if not provided
if [[ -z "$COLLECTION" ]]; then
    COLLECTION="templates/ps1/${BAND}"
fi

# ==========================================
# Setup LSST Stack
# ==========================================

log_info "Setting up LSST Stack..."

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

# Validate repository
if [[ -z "${REPO:-}" ]]; then
    error "REPO not set. Please set REPO in .env or environment"
fi

if [[ ! -d "$REPO" ]]; then
    error "Butler repository not found: $REPO"
fi

# ==========================================
# Build Python Command
# ==========================================

PYTHON_SCRIPT="$OBS_NICKEL/scripts/python/pipeline_tools/ingest_ps1_template.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    error "PS1 ingestion script not found: $PYTHON_SCRIPT"
fi

# Use LSST Python
PYTHON_CMD="/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python"

PYTHON_ARGS=(
    "$PYTHON_SCRIPT"
    --repo "$REPO"
    --ra "$RA"
    --dec "$DEC"
    --band "$BAND"
    --collection "$COLLECTION"
    --size "$CUTOUT_SIZE"
    --output-dir "$OUTPUT_DIR"
)

[[ -n "$TRACT" ]] && PYTHON_ARGS+=(--tract "$TRACT")
[[ -n "$PS1_BAND" ]] && PYTHON_ARGS+=(--ps1-band "$PS1_BAND")
[[ -n "$PS1_FITS" ]] && PYTHON_ARGS+=(--ps1-fits "$PS1_FITS")
[[ "$SKIP_DOWNLOAD" == "true" ]] && PYTHON_ARGS+=(--skip-download)
[[ "$SKIP_INGEST" == "true" ]] && PYTHON_ARGS+=(--skip-ingest)
[[ "$VERBOSE" == "true" ]] && PYTHON_ARGS+=(--verbose)

# ==========================================
# Print Configuration
# ==========================================

log_section "PS1 Template Ingestion"
log_info ""
log_info "Target coordinates:    RA=$RA, Dec=$DEC"
log_info "Nickel band:           $BAND"
log_info "Collection:            $COLLECTION"
[[ -n "$TRACT" ]] && log_info "Tract:                 $TRACT" || log_info "Tract:                 auto-determine"
log_info "Cutout size:           ${CUTOUT_SIZE}°"
log_info "Output directory:      $OUTPUT_DIR"
log_info ""

# ==========================================
# Run Ingestion
# ==========================================

log_info "Running PS1 template ingestion..."
log_info ""

if "$PYTHON_CMD" "${PYTHON_ARGS[@]}"; then
    log_info ""
    log_section "PS1 Template Ingestion Complete"
    log_info ""
    log_info "Template collection: $COLLECTION"
    log_info ""
    log_info "Verify ingestion:"
    log_info "  butler query-datasets $REPO template_coadd \\"
    log_info "    --collections $COLLECTION"
    log_info ""
    log_info "Use in DIA pipeline:"
    log_info "  ./scripts/pipeline/40_diff_imaging.sh \\"
    log_info "    --night YYYYMMDD \\"
    log_info "    --template $COLLECTION"
    log_info ""
    exit 0
else
    error "PS1 template ingestion failed"
fi
