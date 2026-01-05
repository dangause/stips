#!/usr/bin/env bash
#
# ingest_ps1_for_field.sh - Ingest PS1 templates for a specific tract/patch
#
# This script determines which tract/patches cover a field and ingests
# PS1 templates for them. Unlike ingesting by RA/Dec, this ensures the
# PS1 template covers the actual telescope pointings.
#
# Usage:
#   ./scripts/utilities/ingest_ps1_for_field.sh \
#       --tract 2023 \
#       --patch 32 \
#       --band r \
#       --collection templates/ps1/tract2023/r

set -eo pipefail

# Get obs_nickel directory
if [[ -z "${OBS_NICKEL:-}" ]]; then
    OBS_NICKEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    export OBS_NICKEL
fi

# Source environment (only if REPO not already set)
if [[ -z "${REPO:-}" ]] && [[ -f "$OBS_NICKEL/.env" ]]; then
    set -a
    source "$OBS_NICKEL/.env"
    set +a
fi

# Default values
TRACT=""
PATCH=""
BAND=""
COLLECTION=""
SIZE=0.5  # degrees

# ==========================================
# Functions
# ==========================================

usage() {
    head -n 25 "$0" | grep "^#" | sed 's/^# \?//'
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
        --tract)
            TRACT="${2:-}"
            shift 2
            ;;
        --patch)
            PATCH="${2:-}"
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
        --size)
            SIZE="${2:-}"
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

if [[ -z "$TRACT" || -z "$PATCH" || -z "$BAND" || -z "$COLLECTION" ]]; then
    log_error "Missing required arguments"
    usage
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
# Get Patch Center Coordinates
# ==========================================

log_info "Getting patch center coordinates for tract=$TRACT, patch=$PATCH..."

# Use Python to get patch center
PATCH_CENTER=$(python3 <<EOF
import lsst.daf.butler as dafButler
import os

repo = "$REPO"
tract = int("$TRACT")
patch = int("$PATCH")

butler = dafButler.Butler(repo)

skymap_name = os.environ.get("SKYMAP_NAME", "nickelRings-v1")
skymap_collections = os.environ.get("SKYMAPS_CHAIN", "skymaps").split(",")

skymap = butler.get("skyMap", skymap=skymap_name, collections=skymap_collections)

tract_info = skymap[tract]
patch_info = tract_info[patch]

# Get patch center
patch_center = patch_info.getWcs().pixelToSky(patch_info.getOuterBBox().getCenter())

print(f"{patch_center.getRa().asDegrees()} {patch_center.getDec().asDegrees()}")
EOF
)

RA=$(echo $PATCH_CENTER | awk '{print $1}')
DEC=$(echo $PATCH_CENTER | awk '{print $2}')

log_info "Patch center: RA=$RA, Dec=$DEC"

# ==========================================
# Ingest PS1 Template
# ==========================================

log_info "Ingesting PS1 template centered on patch..."

$OBS_NICKEL/scripts/pipeline/08_ingest_ps1_template.sh \
    --ra $RA \
    --dec $DEC \
    --band $BAND \
    --collection $COLLECTION \
    --tract $TRACT \
    --size $SIZE

log_info "Done!"
