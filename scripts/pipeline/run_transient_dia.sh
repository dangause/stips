#!/usr/bin/env bash
#
# run_transient_dia.sh - Optimized DIA workflow for supernova/transient follow-up
#
# This script is a specialized wrapper around run_full_dia.sh with defaults
# optimized for transient campaigns (supernovae, fast transients, etc.)
#
# Key features:
#   - Template date exclusion to avoid transient contamination
#   - Relaxed bad subtraction threshold (transients often in poor seeing)
#   - Object filtering by default (focus on your target)
#   - Automatic tract discovery from coordinates
#
# Usage:
#   ./scripts/pipeline/run_transient_dia.sh \
#     --name "SN2020wnt" \
#     --ra 56.658 --dec 43.229 \
#     --band r \
#     --template-nights template_nights.txt \
#     --science-nights science_nights.txt \
#     --exclude-dates-start 20220101 \
#     --exclude-dates-end 20220301
#
# Required:
#   --name NAME               Transient name (for object filtering and output naming)
#   --ra RA                   Transient RA in degrees
#   --dec DEC                 Transient Dec in degrees
#   --band BAND              Observation band (b/v/r/i)
#   --science-nights FILE     Science observation nights to process
#
# Template Options (choose one):
#   --template-nights FILE    Build template from these nights
#   --template COLLECTION     Use existing template collection
#   --auto-template           Auto-discover template
#
# Optional:
#   --exclude-dates-start YYYYMMDD  Exclude template dates after this (avoid contamination)
#   --exclude-dates-end YYYYMMDD    Exclude template dates before this
#   --bad-sub-threshold NUM         Bad subtraction threshold (default: 0.35 for transients)
#   --jobs N                        Parallel jobs (default: 4)
#   --output-dir DIR                Output directory for results (default: transient_results/)
#   --skip-bootstrap                Skip repository bootstrap
#   --skip-lightcurve               Skip light curve extraction
#   --dry-run                       Print commands without running

# set -euo pipefail

#######################################
# Configuration
#######################################

# Required
TRANSIENT_NAME=""
TRANSIENT_RA=""
TRANSIENT_DEC=""
BAND=""
SCIENCE_NIGHTS_FILE=""

# Template options
TEMPLATE_NIGHTS_FILE=""
TEMPLATE_COLLECTION=""
AUTO_TEMPLATE=false

# Date exclusion for template
EXCLUDE_START=""
EXCLUDE_END=""

# Processing options
BAD_SUB_THRESH="0.35"  # Relaxed for transients (default 0.2 is too strict)
JOBS=4
OUTPUT_DIR=""
SKIP_BOOTSTRAP=false
SKIP_LIGHTCURVE=false
DRY_RUN=false

# Derived
TRACT=""
MATCH_RADIUS="1.0"  # arcsec for light curve extraction

#######################################
# Helpers
#######################################

usage() {
  sed -n '1,50p' "$0" | grep '^#' | sed 's/^# \?//'
  exit 0
}

log() { echo "[$(date '+%H:%M:%S')] $*"; }

#######################################
# Parse arguments
#######################################

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)                    TRANSIENT_NAME="${2:-}"; shift 2;;
    --ra)                      TRANSIENT_RA="${2:-}"; shift 2;;
    --dec)                     TRANSIENT_DEC="${2:-}"; shift 2;;
    --band)                    BAND="${2:-}"; shift 2;;
    --science-nights)          SCIENCE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template-nights)         TEMPLATE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template)                TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --auto-template)           AUTO_TEMPLATE=true; shift 1;;
    --exclude-dates-start)     EXCLUDE_START="${2:-}"; shift 2;;
    --exclude-dates-end)       EXCLUDE_END="${2:-}"; shift 2;;
    --bad-sub-threshold)       BAD_SUB_THRESH="${2:-}"; shift 2;;
    --jobs|-j)                 JOBS="${2:-}"; shift 2;;
    --output-dir)              OUTPUT_DIR="${2:-}"; shift 2;;
    --skip-bootstrap)          SKIP_BOOTSTRAP=true; shift 1;;
    --skip-lightcurve)         SKIP_LIGHTCURVE=true; shift 1;;
    --dry-run)                 DRY_RUN=true; shift 1;;
    -h|--help)                 usage;;
    *) echo "Unknown argument: $1"; usage;;
  esac
done

#######################################
# Validate
#######################################

[[ -z "$TRANSIENT_NAME" ]] && { echo "ERROR: --name required"; exit 2; }
[[ -z "$TRANSIENT_RA" ]] && { echo "ERROR: --ra required"; exit 2; }
[[ -z "$TRANSIENT_DEC" ]] && { echo "ERROR: --dec required"; exit 2; }
[[ -z "$BAND" ]] && { echo "ERROR: --band required"; exit 2; }
[[ -z "$SCIENCE_NIGHTS_FILE" ]] && { echo "ERROR: --science-nights required"; exit 2; }

# Template source validation
if [[ -z "$TEMPLATE_COLLECTION" && "$AUTO_TEMPLATE" == "false" && -z "$TEMPLATE_NIGHTS_FILE" ]]; then
  echo "ERROR: Must provide --template-nights, --template, or --auto-template"
  exit 2
fi

# Date exclusion validation
if [[ -n "$EXCLUDE_START" && -z "$EXCLUDE_END" ]]; then
  echo "ERROR: --exclude-dates-start requires --exclude-dates-end"
  exit 2
fi
if [[ -n "$EXCLUDE_END" && -z "$EXCLUDE_START" ]]; then
  echo "ERROR: --exclude-dates-end requires --exclude-dates-start"
  exit 2
fi

#######################################
# Environment setup
#######################################

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Run from obs_nickel root or set ENV_FILE."
  exit 2
fi

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Default output directory
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="./transient_dia_results/${TRANSIENT_NAME}_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$OUTPUT_DIR"

LOG_FILE="$OUTPUT_DIR/workflow.log"

# Redirect output to log and terminal
exec > >(tee -a "$LOG_FILE")
exec 2>&1

#######################################
# Find tract from coordinates
#######################################

log "======================================="
log "Transient DIA Pipeline"
log "======================================="
log "Transient:         $TRANSIENT_NAME"
log "Coordinates:       RA=$TRANSIENT_RA, Dec=$TRANSIENT_DEC"
log "Band:              $BAND"
log "Science nights:    $SCIENCE_NIGHTS_FILE"
log "Bad sub threshold: $BAD_SUB_THRESH"
log "Output:            $OUTPUT_DIR"
log "======================================="

log "Finding tract for transient coordinates..."

cd "$STACK_DIR"
set +u
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel
set -u

cd "$OBS_NICKEL"

CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
TRACT=$(/opt/anaconda3/envs/${CONDA_ENV}/bin/python3 << PYEOF
import lsst.daf.butler as dafButler
import lsst.geom as geom

butler = dafButler.Butler("$REPO")
skymap = butler.get("skyMap", collections="skymaps", skymap="nickelRings-v1")

coord = geom.SpherePoint($TRANSIENT_RA, $TRANSIENT_DEC, geom.degrees)
tract_info = skymap.findTract(coord)
print(tract_info.getId())
PYEOF
)

log "Tract: $TRACT"

#######################################
# Build run_full_dia.sh arguments
#######################################

FULL_DIA_ARGS=(
  --science-nights "$SCIENCE_NIGHTS_FILE"
  --band "$BAND"
  --tract "$TRACT"
  --object "$TRANSIENT_NAME"
  --jobs "$JOBS"
  --bad-sub-threshold "$BAD_SUB_THRESH"
)

# Template source
if [[ -n "$TEMPLATE_COLLECTION" ]]; then
  FULL_DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
  FULL_DIA_ARGS+=(--skip-template-build)
elif [[ "$AUTO_TEMPLATE" == "true" ]]; then
  FULL_DIA_ARGS+=(--auto-template)
else
  FULL_DIA_ARGS+=(--template-nights "$TEMPLATE_NIGHTS_FILE")
fi

# Bootstrap
[[ "$SKIP_BOOTSTRAP" == "true" ]] && FULL_DIA_ARGS+=(--skip-bootstrap)

# Dry run
[[ "$DRY_RUN" == "true" ]] && FULL_DIA_ARGS+=(--dry-run)

#######################################
# Handle template date exclusion
#######################################

if [[ -n "$EXCLUDE_START" && -n "$EXCLUDE_END" ]]; then
  log ""
  log "Template date exclusion: $EXCLUDE_START to $EXCLUDE_END"
  log "NOTE: Date exclusion requires manual template selection or metadata-aware discovery"
  log "      Using 40_diff_imaging.sh --exclude-start/--exclude-end in DIA step"

  # We'll need to modify the workflow to pass these to 40_diff_imaging.sh
  # For now, warn the user
  log "WARNING: Template date exclusion not yet integrated with run_full_dia.sh"
  log "         Use 40_diff_imaging.sh directly with --exclude-start/--exclude-end"
fi

#######################################
# Run DIA pipeline
#######################################

log ""
log "Running DIA pipeline..."
log "Command: ./scripts/pipeline/run_full_dia.sh ${FULL_DIA_ARGS[*]}"
log ""

if [[ "$DRY_RUN" == "false" ]]; then
  ./scripts/pipeline/run_full_dia.sh "${FULL_DIA_ARGS[@]}"
else
  log "[DRY-RUN] Would run: ./scripts/pipeline/run_full_dia.sh ${FULL_DIA_ARGS[*]}"
fi

#######################################
# Extract light curve
#######################################

if [[ "$SKIP_LIGHTCURVE" == "false" && "$DRY_RUN" == "false" ]]; then
  log ""
  log "======================================="
  log "Extracting light curve"
  log "======================================="

  LC_OUTPUT="$OUTPUT_DIR/${TRANSIENT_NAME}_lightcurve.ecsv"

  # Find all DIA collections created
  SCIENCE_NIGHTS=($(cat "$SCIENCE_NIGHTS_FILE" | sed 's/#.*//' | sed '/^\s*$/d'))
  DIA_COLLECTIONS=""

  for night in "${SCIENCE_NIGHTS[@]}"; do
    coll=$(butler query-collections "$REPO" 2>/dev/null | \
           grep "Nickel/runs/${night}/diff/" | tail -n1 || true)
    if [[ -n "$coll" ]]; then
      if [[ -z "$DIA_COLLECTIONS" ]]; then
        DIA_COLLECTIONS="$coll"
      else
        DIA_COLLECTIONS="${DIA_COLLECTIONS},${coll}"
      fi
    fi
  done

  if [[ -z "$DIA_COLLECTIONS" ]]; then
    log "WARNING: No DIA collections found, skipping light curve extraction"
  else
    log "DIA collections: $DIA_COLLECTIONS"
    log "Extracting light curve to: $LC_OUTPUT"

    if [[ -f "scripts/python/pipeline_tools/extract_lightcurve.py" ]]; then
      /opt/anaconda3/envs/${CONDA_ENV}/bin/python \
        scripts/python/pipeline_tools/extract_lightcurve.py \
        --repo "$REPO" \
        --collection "$DIA_COLLECTIONS" \
        --ra "$TRANSIENT_RA" \
        --dec "$TRANSIENT_DEC" \
        --radius "$MATCH_RADIUS" \
        --band "$BAND" \
        --min-snr 3.0 \
        --output "$LC_OUTPUT" || {
        log "WARNING: Light curve extraction failed (may be no detections)"
      }

      if [[ -f "$LC_OUTPUT" ]]; then
        log "Light curve saved: $LC_OUTPUT"
        log ""
        log "Summary:"
        head -20 "$LC_OUTPUT"
      fi
    else
      log "WARNING: extract_lightcurve.py not found, skipping"
    fi
  fi
fi

#######################################
# Summary
#######################################

log ""
log "======================================="
log "Transient DIA Complete"
log "======================================="
log "Transient:    $TRANSIENT_NAME"
log "Tract:        $TRACT"
log "Band:         $BAND"
log "Output:       $OUTPUT_DIR"
log "Log:          $LOG_FILE"
if [[ -f "$LC_OUTPUT" ]]; then
  log "Light curve:  $LC_OUTPUT"
fi
log "======================================="
log ""
log "Next steps:"
log "  1. Review light curve: $LC_OUTPUT"
log "  2. Inspect difference images in DS9/Firefly"
log "  3. Check DIA quality in logs"
log ""
