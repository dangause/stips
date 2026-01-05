#!/usr/bin/env bash
#
# check_template_coverage.sh - Check template availability for target coordinates
#
# This script checks if templates (internal or PS1) exist for given coordinates,
# helping you decide whether to build new templates or use existing ones.
#
# Usage:
#   ./scripts/utilities/check_template_coverage.sh \
#       --ra 150.123 \
#       --dec 2.456 \
#       --band r
#
# Options:
#   --ra DEGREES      : Right ascension in degrees (required)
#   --dec DEGREES     : Declination in degrees (required)
#   --band BAND       : Filter band (b, v, r, i)
#   --check-ps1       : Also check if PS1 coverage is available
#   --tract TRACT     : Override tract determination

set -euo pipefail

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
RA=""
DEC=""
BAND=""
CHECK_PS1=false
TRACT=""

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
        --check-ps1)
            CHECK_PS1=true
            shift
            ;;
        --tract)
            TRACT="${2:-}"
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

if [[ -z "$RA" || -z "$DEC" ]]; then
    log_error "Missing required arguments: --ra and --dec"
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
# Check Template Coverage
# ==========================================

log_info "========================================="
log_info "Template Coverage Check"
log_info "========================================="
log_info ""
log_info "Coordinates: RA=${RA}°, Dec=${DEC}°"
[[ -n "$BAND" ]] && log_info "Band filter: $BAND"
[[ -n "$TRACT" ]] && log_info "Tract: $TRACT (user-specified)"
log_info ""

# Determine tract if not specified
if [[ -z "$TRACT" ]]; then
    log_info "Determining tract from coordinates..."

    # Use Python to determine tract
    TRACT=$(python3 <<EOF
import lsst.daf.butler as dafButler
import lsst.geom as geom
import os

repo = "$REPO"
ra = float("$RA")
dec = float("$DEC")

butler = dafButler.Butler(repo)

skymap_name = os.environ.get("SKYMAP_NAME", "nickelRings-v1")
skymap_collections = os.environ.get("SKYMAPS_CHAIN", "skymaps/nickelRings,skymaps").split(",")

skymap = butler.get("skyMap", skymap=skymap_name, collections=skymap_collections)

coord = geom.SpherePoint(ra, dec, geom.degrees)
tract_info = skymap.findTract(coord)
print(tract_info.getId())
EOF
)

    log_info "  → Tract: $TRACT"
fi

log_info ""
log_info "Checking for existing templates..."
log_info ""

# Build search criteria
BAND_FILTER=""
if [[ -n "$BAND" ]]; then
    BAND_FILTER="/$BAND"
fi

# Check internal templates (templates/deep and templates/)
log_info "=== Internal Templates ==="
INTERNAL_TEMPLATES=$(butler query-datasets "$REPO" template_coadd \
    --collections "templates/*" \
    --where "tract=$TRACT" 2>/dev/null | tail -n +3 || true)

if [[ -n "$INTERNAL_TEMPLATES" && "$INTERNAL_TEMPLATES" != "0 rows" ]]; then
    echo "$INTERNAL_TEMPLATES" | grep -E "${BAND_FILTER}$" || {
        echo "No internal templates found for tract $TRACT${BAND_FILTER:+ and band $BAND}"
    }
else
    echo "No internal templates found for tract $TRACT"
fi

echo ""

# Check PS1 templates
log_info "=== PS1 Templates ==="
PS1_TEMPLATES=$(butler query-datasets "$REPO" template_coadd \
    --collections "templates/ps1/*" \
    --where "tract=$TRACT" 2>/dev/null | tail -n +3 || true)

if [[ -n "$PS1_TEMPLATES" && "$PS1_TEMPLATES" != "0 rows" ]]; then
    echo "$PS1_TEMPLATES" | grep -E "${BAND_FILTER}$" || {
        echo "No PS1 templates found for tract $TRACT${BAND_FILTER:+ and band $BAND}"
    }
else
    echo "No PS1 templates found for tract $TRACT"
fi

echo ""

# Check PS1 survey coverage (if requested)
if [[ "$CHECK_PS1" == "true" ]]; then
    log_info "=== PS1 Survey Coverage ==="
    log_info "Checking if PS1 has coverage at this position..."

    # Use Python to query PS1 footprint
    python3 <<EOF
from astropy.coordinates import SkyCoord
import astropy.units as u

ra = float("$RA")
dec = float("$DEC")
coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")

# PS1 survey coverage:
# Dec: -30° to +90°
# Full sky north of -30°, but with gaps

if coord.dec.deg < -30:
    print(f"  ❌ Outside PS1 coverage (Dec={coord.dec.deg:.1f}° < -30°)")
    print("  → Cannot use PS1 templates for this field")
elif coord.dec.deg > 90:
    print(f"  ❌ Invalid declination: {coord.dec.deg:.1f}°")
else:
    print(f"  ✓ Inside PS1 footprint (Dec={coord.dec.deg:.1f}°)")
    print("  → PS1 templates should be available")
    print("")
    print("  To ingest PS1 template:")
    print(f"    ./scripts/pipeline/08_ingest_ps1_template.sh \\")
    print(f"      --ra {ra} \\")
    print(f"      --dec {dec} \\")
    if "$BAND":
        print(f"      --band $BAND \\")
    print(f"      --tract $TRACT")
EOF

    echo ""
fi

# ==========================================
# Summary and Recommendations
# ==========================================

log_info "========================================="
log_info "Recommendations"
log_info "========================================="
log_info ""

# Count available templates
INTERNAL_COUNT=$(echo "$INTERNAL_TEMPLATES" | grep -c "template_coadd" || echo "0")
PS1_COUNT=$(echo "$PS1_TEMPLATES" | grep -c "template_coadd" || echo "0")

if [[ "$INTERNAL_COUNT" -gt 0 ]]; then
    log_info "✓ Internal templates available ($INTERNAL_COUNT found)"
    log_info "  → Use: --template <collection> or --auto-template"
elif [[ "$PS1_COUNT" -gt 0 ]]; then
    log_info "✓ PS1 templates available ($PS1_COUNT found)"
    log_info "  → Use: --template templates/ps1/... or --prefer-ps1 --auto-template"
else
    log_info "❌ No templates found for this field"
    log_info ""
    log_info "Options:"
    log_info "  1. Build internal template from Nickel observations:"
    log_info "     ./scripts/pipeline/30_coadds.sh --tract $TRACT --band ${BAND:-r} ..."
    log_info ""
    log_info "  2. Ingest PS1 template (if position has coverage):"
    log_info "     ./scripts/pipeline/08_ingest_ps1_template.sh \\"
    log_info "       --ra $RA --dec $DEC --band ${BAND:-r} --tract $TRACT"
fi

log_info ""

exit 0
