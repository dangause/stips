#!/usr/bin/env bash
#
# run_variable_dia.sh - Optimized DIA workflow for variable star monitoring
#
# This script is a specialized wrapper around run_full_dia.sh with defaults
# optimized for variable star campaigns (Cepheids, RR Lyrae, eclipsing binaries, etc.)
#
# Key features:
#   - Strict quality thresholds (variables need clean photometry)
#   - Multi-epoch processing (all observations of the same field)
#   - Optional field-based processing (no object filter by default)
#   - Automatic multi-band support
#
# Usage:
#   ./scripts/pipeline/run_variable_dia.sh \
#     --name "M33_field1" \
#     --ra 23.462 --dec 30.660 \
#     --bands r,i \
#     --observation-nights all_nights.txt \
#     --template-nights template_nights.txt \
#     --output-dir m33_variables
#
# Required:
#   --name NAME               Field/target name (for output naming)
#   --ra RA                   Field center RA in degrees
#   --dec DEC                 Field center Dec in degrees
#   --bands BANDS            Comma-separated observation bands (e.g., r,i or b,v,r,i)
#   --observation-nights FILE All observation nights to process
#
# Template Options (choose one):
#   --template-nights FILE    Build template from these nights
#   --template COLLECTION     Use existing template collection (band-specific)
#   --auto-template           Auto-discover template
#
# Optional:
#   --object NAME               Filter by specific object (for targeted variable)
#   --bad-sub-threshold NUM     Bad subtraction threshold (default: 0.2, strict)
#   --min-template-nights N     Minimum nights for template (default: 5)
#   --jobs N                    Parallel jobs (default: 4)
#   --output-dir DIR            Output directory (default: variable_results/)
#   --skip-bootstrap            Skip repository bootstrap
#   --skip-lightcurve           Skip light curve extraction (extract manually later)
#   --extract-catalog           Extract full DIA catalog for all sources
#   --dry-run                   Print commands without running

# set -euo pipefail

#######################################
# Configuration
#######################################

# Required
FIELD_NAME=""
FIELD_RA=""
FIELD_DEC=""
BANDS=""
OBSERVATION_NIGHTS_FILE=""

# Template options
TEMPLATE_NIGHTS_FILE=""
TEMPLATE_COLLECTION=""
AUTO_TEMPLATE=false

# Processing options
OBJECT_FILTER=""
BAD_SUB_THRESH="0.2"  # Strict for variables (good photometry needed)
MIN_TEMPLATE_NIGHTS=5
JOBS=4
OUTPUT_DIR=""
SKIP_BOOTSTRAP=false
SKIP_LIGHTCURVE=false
EXTRACT_CATALOG=false
DRY_RUN=false

# Derived
TRACT=""

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
    --name)                    FIELD_NAME="${2:-}"; shift 2;;
    --ra)                      FIELD_RA="${2:-}"; shift 2;;
    --dec)                     FIELD_DEC="${2:-}"; shift 2;;
    --bands)                   BANDS="${2:-}"; shift 2;;
    --observation-nights)      OBSERVATION_NIGHTS_FILE="${2:-}"; shift 2;;
    --template-nights)         TEMPLATE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template)                TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --auto-template)           AUTO_TEMPLATE=true; shift 1;;
    --object)                  OBJECT_FILTER="${2:-}"; shift 2;;
    --bad-sub-threshold)       BAD_SUB_THRESH="${2:-}"; shift 2;;
    --min-template-nights)     MIN_TEMPLATE_NIGHTS="${2:-}"; shift 2;;
    --jobs|-j)                 JOBS="${2:-}"; shift 2;;
    --output-dir)              OUTPUT_DIR="${2:-}"; shift 2;;
    --skip-bootstrap)          SKIP_BOOTSTRAP=true; shift 1;;
    --skip-lightcurve)         SKIP_LIGHTCURVE=true; shift 1;;
    --extract-catalog)         EXTRACT_CATALOG=true; shift 1;;
    --dry-run)                 DRY_RUN=true; shift 1;;
    -h|--help)                 usage;;
    *) echo "Unknown argument: $1"; usage;;
  esac
done

#######################################
# Validate
#######################################

[[ -z "$FIELD_NAME" ]] && { echo "ERROR: --name required"; exit 2; }
[[ -z "$FIELD_RA" ]] && { echo "ERROR: --ra required"; exit 2; }
[[ -z "$FIELD_DEC" ]] && { echo "ERROR: --dec required"; exit 2; }
[[ -z "$BANDS" ]] && { echo "ERROR: --bands required"; exit 2; }
[[ -z "$OBSERVATION_NIGHTS_FILE" ]] && { echo "ERROR: --observation-nights required"; exit 2; }

# Template source validation
if [[ -z "$TEMPLATE_COLLECTION" && "$AUTO_TEMPLATE" == "false" && -z "$TEMPLATE_NIGHTS_FILE" ]]; then
  echo "ERROR: Must provide --template-nights, --template, or --auto-template"
  exit 2
fi

#######################################
# Environment setup
#######################################

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Run from obs_nickel root or set ENV_FILE."; exit 2;
fi

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a
# Resolve repo root + package path for monorepo layout.
# shellcheck source=/dev/null
source "$(dirname "$0")/../utilities/repo_paths.sh"

# Default output directory
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="./variable_dia_results/${FIELD_NAME}_$(date +%Y%m%d_%H%M%S)"
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
log "Variable Star DIA Pipeline"
log "======================================="
log "Field:             $FIELD_NAME"
log "Coordinates:       RA=$FIELD_RA, Dec=$FIELD_DEC"
log "Bands:             $BANDS"
log "Observation nights: $OBSERVATION_NIGHTS_FILE"
log "Bad sub threshold: $BAD_SUB_THRESH"
log "Output:            $OUTPUT_DIR"
log "======================================="

log "Finding tract for field coordinates..."

cd "$STACK_DIR"
set +u
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel
set -u

cd "$REPO_ROOT"

CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
TRACT=$(/opt/anaconda3/envs/${CONDA_ENV}/bin/python3 << PYEOF
import lsst.daf.butler as dafButler
import lsst.geom as geom

butler = dafButler.Butler("$REPO")
skymap = butler.get("skyMap", collections="skymaps", skymap="nickelRings-v1")

coord = geom.SpherePoint($FIELD_RA, $FIELD_DEC, geom.degrees)
tract_info = skymap.findTract(coord)
print(tract_info.getId())
PYEOF
)

log "Tract: $TRACT"

#######################################
# Validate template nights
#######################################

if [[ -n "$TEMPLATE_NIGHTS_FILE" ]]; then
  TEMPLATE_NIGHT_COUNT=$(cat "$TEMPLATE_NIGHTS_FILE" | sed 's/#.*//' | sed '/^\s*$/d' | wc -l)
  log "Template nights: $TEMPLATE_NIGHT_COUNT"

  if [[ $TEMPLATE_NIGHT_COUNT -lt $MIN_TEMPLATE_NIGHTS ]]; then
    log "WARNING: Template has only $TEMPLATE_NIGHT_COUNT nights (recommended: ≥$MIN_TEMPLATE_NIGHTS)"
    log "         Consider adding more nights for a deeper template"
  fi
fi

#######################################
# Process each band
#######################################

IFS=',' read -ra BAND_ARRAY <<< "$BANDS"

log ""
log "Processing ${#BAND_ARRAY[@]} band(s): ${BAND_ARRAY[*]}"
log ""

for BAND in "${BAND_ARRAY[@]}"; do
  BAND=$(echo "$BAND" | tr -d ' ')  # Trim whitespace

  log "======================================="
  log "Processing band: $BAND"
  log "======================================="

  # Build run_full_dia.sh arguments
  FULL_DIA_ARGS=(
    --science-nights "$OBSERVATION_NIGHTS_FILE"
    --band "$BAND"
    --tract "$TRACT"
    --jobs "$JOBS"
    --bad-sub-threshold "$BAD_SUB_THRESH"
  )

  # Object filter (optional for variables)
  if [[ -n "$OBJECT_FILTER" ]]; then
    FULL_DIA_ARGS+=(--object "$OBJECT_FILTER")
  fi

  # Template source
  if [[ -n "$TEMPLATE_COLLECTION" ]]; then
    # For multi-band, assume template collection is band-specific
    BAND_TEMPLATE="${TEMPLATE_COLLECTION}/${BAND}"
    FULL_DIA_ARGS+=(--template "$BAND_TEMPLATE")
    FULL_DIA_ARGS+=(--skip-template-build)
  elif [[ "$AUTO_TEMPLATE" == "true" ]]; then
    FULL_DIA_ARGS+=(--auto-template)
  else
    FULL_DIA_ARGS+=(--template-nights "$TEMPLATE_NIGHTS_FILE")
  fi

  # Bootstrap (only for first band)
  if [[ "$SKIP_BOOTSTRAP" == "true" || "$BAND" != "${BAND_ARRAY[0]}" ]]; then
    FULL_DIA_ARGS+=(--skip-bootstrap)
  fi

  # Dry run
  [[ "$DRY_RUN" == "true" ]] && FULL_DIA_ARGS+=(--dry-run)

  #######################################
  # Run DIA for this band
  #######################################

  log "Running DIA for band $BAND..."
  log "Command: ./scripts/pipeline/run_full_dia.sh ${FULL_DIA_ARGS[*]}"
  log ""

  if [[ "$DRY_RUN" == "false" ]]; then
    ./scripts/pipeline/run_full_dia.sh "${FULL_DIA_ARGS[@]}"
  else
    log "[DRY-RUN] Would run: ./scripts/pipeline/run_full_dia.sh ${FULL_DIA_ARGS[*]}"
  fi

  log ""
  log "Band $BAND complete"
  log ""
done

#######################################
# Extract catalogs
#######################################

if [[ "$EXTRACT_CATALOG" == "true" && "$DRY_RUN" == "false" ]]; then
  log "======================================="
  log "Extracting DIA source catalogs"
  log "======================================="

  for BAND in "${BAND_ARRAY[@]}"; do
    BAND=$(echo "$BAND" | tr -d ' ')

    CATALOG_OUTPUT="$OUTPUT_DIR/${FIELD_NAME}_${BAND}_dia_sources.parquet"

    log "Extracting band $BAND catalog to: $CATALOG_OUTPUT"

    # Find all DIA collections for this band
    OBSERVATION_NIGHTS=($(cat "$OBSERVATION_NIGHTS_FILE" | sed 's/#.*//' | sed '/^\s*$/d'))
    DIA_COLLECTIONS=""

    for night in "${OBSERVATION_NIGHTS[@]}"; do
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

    if [[ -n "$DIA_COLLECTIONS" ]]; then
      # Extract full DIA catalog
      log "  Collections: $DIA_COLLECTIONS"

      # Use butler to get catalogs (user will need to process with Python)
      log "  Collections saved, use Python/butler to extract full catalogs"
      echo "$DIA_COLLECTIONS" > "$OUTPUT_DIR/${FIELD_NAME}_${BAND}_dia_collections.txt"
    else
      log "  WARNING: No DIA collections found for band $BAND"
    fi
  done
fi

#######################################
# Summary
#######################################

log ""
log "======================================="
log "Variable Star DIA Complete"
log "======================================="
log "Field:        $FIELD_NAME"
log "Tract:        $TRACT"
log "Bands:        ${BAND_ARRAY[*]}"
log "Output:       $OUTPUT_DIR"
log "Log:          $LOG_FILE"
log "======================================="
log ""
log "Next steps:"
log "  1. Extract light curves for specific variables:"
log "     obsn-dia-lightcurve \\"
log "       --repo \$REPO \\"
log "       --collection <DIA_COLLECTION> \\"
log "       --ra <VAR_RA> --dec <VAR_DEC> \\"
log "       --radius 1.0 --band <BAND> \\"
log "       --output <FIELD_NAME>_<VAR_NAME>_lc.ecsv"
log ""
log "  2. Or extract full field catalog for variable search:"
log "     butler get \$REPO dia_source_unfiltered \\"
log "       --collections <DIA_COLLECTION> \\"
log "       --where \"instrument='Nickel' AND band='$BAND'\""
log ""
log "  3. Inspect difference images in DS9/Firefly"
log "  4. Run period-finding on light curves (Lomb-Scargle, PDM, etc.)"
log ""
