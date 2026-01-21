#!/usr/bin/env bash
#
# run_dia_multi_band.sh — Download (optional) + calibs + science once, then DIA across multiple bands
# Usage example:
#   ./scripts/pipeline/run_dia_multi_band.sh \
#     --template-nights scripts/config/2020wnt/template_nights.txt \
#     --science-nights  scripts/config/2020wnt/sn_nights.txt \
#     --bands "b,v,r,i" \
#     --tract 1825 \
#     --object "2020wnt" \
#     --jobs 4
#
# Notes:
#   - Optionally downloads raws from archive per night (01_download_archive.sh)
#   - Runs 10_calibs and 20_science once per night (no repetition per band)
#   - Builds a template per band (30_coadds) unless --skip-template-build or --auto-template is set
#   - Runs DIA (40_diff_imaging) per science night per band
#   - Uses hierarchical logging system
#
# set -euo pipefail

# Source logging utilities
source "$(dirname "$0")/../utilities/logging.sh"

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a
if [[ -f "${PWD}/scripts/utilities/repo_paths.sh" ]]; then
  # shellcheck disable=SC1091
  source "${PWD}/scripts/utilities/repo_paths.sh"
fi
export REPO_ROOT="${REPO_ROOT:-${PWD}}"
export OBS_NICKEL="${OBS_NICKEL:-${REPO_ROOT}/packages/obs_nickel}"
# Force local packages ahead of stack installs for PipelineTask imports.
export PYTHONPATH="${OBS_NICKEL}/python:${REPO_ROOT}/packages/obs_nickel_data/python:${PYTHONPATH:-}"
########################################
# Defaults / CLI
########################################
TEMPLATE_NIGHTS_FILE=""
SCIENCE_NIGHTS_FILE=""
OBS_TEMPLATE_NIGHTS_FILE=""
OBS_SCIENCE_NIGHTS_FILE=""
TEMPLATE_REFERENCE_FILE=""
SCIENCE_REFERENCE_FILE=""
NIGHT_TIMEZONE="${NIGHT_TIMEZONE:-America/Los_Angeles}"
BANDS="r"
TRACT=""
RA=""
DEC=""
SKYMAP="${SKYMAP:-nickelRings-v1}"
OBJECT_FILTER=""
JOBS="${JOBS:-4}"
BAD_SUB_THRESH=""
SCIENCE_CONFIG=""
DIA_ANALYSIS=false
DIA_LIGHTCURVE_TASK=false
SKIP_DOWNLOAD=false
DOWNLOAD_OVERWRITE=false
SKIP_TEMPLATE_BUILD=false
AUTO_TEMPLATE=false
USE_PS1_TEMPLATES=false
PS1_DEGRADE_SEEING=""
DRY_RUN=false
CONTINUE_ON_ERROR=false
SKIP_BOOTSTRAP=false
SKIP_CALIBS=false
SKIP_SCIENCE=false
SKIP_DIA=false
OVERWRITE_TEMPLATES=false
FORCED_PHOT=false
FORCED_PHOT_LIGHTCURVE=false
FORCED_PHOT_IMAGE_TYPE="diffim"
FORCED_PHOT_COORDS_FILE=""
FORCED_PHOT_RA=""
FORCED_PHOT_DEC=""
LIGHTCURVE=false
LIGHTCURVE_RADIUS="1.0"
LIGHTCURVE_MIN_SNR="3.0"
LIGHTCURVE_DATASET_TYPE="dia_source_unfiltered"
LIGHTCURVE_BAND=""
LIGHTCURVE_NAME=""
LIGHTCURVE_OUTPUT_DIR=""
FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION=""

# Exit codes: 0=success, 1=failures with --continue-on-error, 2=fatal error
EXIT_CODE=0
FAILED_DOWNLOADS=()
FAILED_CALIBS=()
FAILED_SCIENCE=()
FAILED_TEMPLATE=()
FAILED_DIA=()
FAILED_FORCED_PHOT=()
FORCED_PHOT_VISIT_COLLECTIONS=()
FORCED_PHOT_DIFFIM_COLLECTIONS=()

usage() {
  cat <<USAGE
Usage: $0 --template-nights FILE --science-nights FILE --bands "r,i" [--tract TRACT | --ra RA --dec DEC] [options]

Required (choose one method):
  Method 1: UT day_obs files (simple text files)
    --template-nights FILE   UT day_obs nights file for template build (YYYYMMDD per line)
    --science-nights FILE    UT day_obs nights file for science/DIA (YYYYMMDD per line)

  Method 2: Observing-night files (auto-convert to UT day_obs)
    --observing-template-nights FILE   Observing-night file (local date) to auto-convert to UT day_obs
    --observing-science-nights FILE    Observing-night file (local date) to auto-convert to UT day_obs

  Method 3: Reference YAML files (maps observing nights → UT day_obs, recommended)
    --template-reference FILE   YAML file mapping template observing nights to UT day_obs
    --science-reference FILE    YAML file mapping science observing nights to UT day_obs

  --bands LIST             Comma-separated bands (e.g., "r" or "b,v,r,i")

Tract Selection (choose one):
  --tract TRACT            Tract number (must be numeric)
    OR
  --ra RA --dec DEC        RA/Dec in degrees (auto-determines tract)
  --skymap NAME            Skymap name for RA/Dec lookup (default: nickelRings-v1)

Optional:
  --night-timezone TZ      Timezone for observing-night conversion (default: America/Los_Angeles)
  --object NAME            OBJECT filter for science/DIA
  --science-config FILE    Override calibrateImage config for 20_science.sh
  --jobs N                 Parallel jobs for pipeline tasks (default: ${JOBS})
  --bad-sub-threshold X    Override badSubtractionRatioThreshold for DIA
  --dia-analysis           Run DIA diagnostic analysis tasks during diff imaging
  --skip-download          Skip archive downloads (assumes raw data already present)
  --download-overwrite     Re-download even if files exist (passes --overwrite)

Template Options:
  --skip-template-build    Skip 30_coadds (use existing templates)
  --auto-template          Let 40_diff_imaging auto-discover templates (skips 30)
  --use-ps1-templates      Use PS1 templates (auto-download/ingest if missing)
  --ps1-degrade-seeing N   Convolve PS1 templates to N arcsec FWHM (e.g., 2.0)
  --overwrite-templates    Force rebuild templates even if collections/runs already exist

Forced Photometry:
  --forced-phot            Run forced photometry at RA/Dec after DIA (per band/night)
  --forced-phot-lightcurve Generate forced photometry lightcurve tables/plots (PipelineTask)
  --forced-phot-image-type TYPE  visit|diffim|both (default: diffim)
  --forced-phot-coords-file FILE CSV with ra,dec columns (optional)
  --forced-phot-ra RA      RA in degrees for forced photometry (defaults to --ra)
  --forced-phot-dec DEC    Dec in degrees for forced photometry (defaults to --dec)

Lightcurve Analysis:
  --dia-lightcurve-task    Run DIA lightcurve PipelineTask (writes to Butler)
  --lightcurve             Extract DIA lightcurve and generate plot after pipeline
  --lightcurve-radius ARCSEC  Match radius in arcsec (default: 1.0)
  --lightcurve-min-snr N      Minimum S/N filter (default: 3.0)
  --lightcurve-dataset-type TYPE  Dataset type (default: dia_source_unfiltered)
  --lightcurve-band BAND     Restrict lightcurve to a single band
  --lightcurve-name NAME     Name for plot title/filename (defaults to --object or RA/Dec)
  --lightcurve-output-dir DIR Output directory (default: run log dir)

Pipeline Control:
  --skip-bootstrap         Skip repository bootstrap (fail if repo doesn't exist)
  --skip-calibs            Skip calibration processing (10_calibs.sh)
  --skip-science           Skip science processing (20_science.sh)
  --skip-dia               Skip difference imaging (use existing DIA outputs)
  --continue-on-error      Continue processing remaining nights/bands after failures
  --dry-run                Print commands without executing

Reference YAML Format:
  object: "TARGET_NAME"
  nights:
    20201207:               # Observing night (local date, used for collection paths)
      v: [76482094]         # Visit IDs for each filter
      r: [76482095, 76482092]
      b: [76482093]
      i: [76482096]
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-nights) TEMPLATE_NIGHTS_FILE="${2:-}"; shift; shift;;
    --science-nights)  SCIENCE_NIGHTS_FILE="${2:-}"; shift; shift;;
    --observing-template-nights) OBS_TEMPLATE_NIGHTS_FILE="${2:-}"; shift; shift;;
    --observing-science-nights)  OBS_SCIENCE_NIGHTS_FILE="${2:-}"; shift; shift;;
    --template-reference) TEMPLATE_REFERENCE_FILE="${2:-}"; shift; shift;;
    --science-reference)  SCIENCE_REFERENCE_FILE="${2:-}"; shift; shift;;
    --night-timezone) NIGHT_TIMEZONE="${2:-}"; shift; shift;;
    --bands)           BANDS="${2:-}"; shift; shift;;
    --tract)           TRACT="${2:-}"; shift; shift;;
    --ra)              RA="${2:-}"; shift; shift;;
    --dec)             DEC="${2:-}"; shift; shift;;
    --skymap)          SKYMAP="${2:-}"; shift; shift;;
    --object)          OBJECT_FILTER="${2:-}"; shift; shift;;
    --science-config)  SCIENCE_CONFIG="${2:-}"; shift; shift;;
    --jobs|-j)         JOBS="${2:-4}"; shift; shift;;
    --bad-sub-threshold) BAD_SUB_THRESH="${2:-}"; shift; shift;;
    --dia-analysis)   DIA_ANALYSIS=true; shift;;
    --dia-lightcurve-task) DIA_LIGHTCURVE_TASK=true; shift;;
    --skip-download)   SKIP_DOWNLOAD=true; shift;;
    --download-overwrite) DOWNLOAD_OVERWRITE=true; shift;;
    --skip-template-build) SKIP_TEMPLATE_BUILD=true; shift;;
    --auto-template)   AUTO_TEMPLATE=true; shift;;
    --use-ps1-templates) USE_PS1_TEMPLATES=true; shift;;
    --ps1-degrade-seeing) PS1_DEGRADE_SEEING="${2:-}"; shift; shift;;
    --overwrite-templates) OVERWRITE_TEMPLATES=true; shift;;
    --dry-run)         DRY_RUN=true; shift;;
    --continue-on-error) CONTINUE_ON_ERROR=true; shift;;
    --skip-bootstrap)  SKIP_BOOTSTRAP=true; shift;;
    --skip-calibs)     SKIP_CALIBS=true; shift;;
    --skip-science)    SKIP_SCIENCE=true; shift;;
    --skip-dia)        SKIP_DIA=true; shift;;
    --forced-phot)     FORCED_PHOT=true; shift;;
    --forced-phot-lightcurve) FORCED_PHOT_LIGHTCURVE=true; shift;;
    --forced-phot-image-type) FORCED_PHOT_IMAGE_TYPE="${2:-}"; shift; shift;;
    --forced-phot-coords-file) FORCED_PHOT_COORDS_FILE="${2:-}"; shift; shift;;
    --forced-phot-ra)  FORCED_PHOT_RA="${2:-}"; shift; shift;;
    --forced-phot-dec) FORCED_PHOT_DEC="${2:-}"; shift; shift;;
    --lightcurve)      LIGHTCURVE=true; shift;;
    --lightcurve-radius) LIGHTCURVE_RADIUS="${2:-}"; shift; shift;;
    --lightcurve-min-snr) LIGHTCURVE_MIN_SNR="${2:-}"; shift; shift;;
    --lightcurve-dataset-type) LIGHTCURVE_DATASET_TYPE="${2:-}"; shift; shift;;
    --lightcurve-band) LIGHTCURVE_BAND="${2:-}"; shift; shift;;
    --lightcurve-name) LIGHTCURVE_NAME="${2:-}"; shift; shift;;
    --lightcurve-output-dir) LIGHTCURVE_OUTPUT_DIR="${2:-}"; shift; shift;;
  -h|--help)         usage;;
  *)
    if [[ -n "$1" ]]; then
      echo "Unknown arg: $1";
    else
      echo "Unknown empty arg (this shouldn't happen)";
    fi
    usage;;
  esac
done

# Validate that only one method is used per nights type (template/science)
TEMPLATE_METHODS=0
[[ -n "$TEMPLATE_NIGHTS_FILE" ]] && ((TEMPLATE_METHODS++))
[[ -n "$OBS_TEMPLATE_NIGHTS_FILE" ]] && ((TEMPLATE_METHODS++))
[[ -n "$TEMPLATE_REFERENCE_FILE" ]] && ((TEMPLATE_METHODS++))
if [[ $TEMPLATE_METHODS -gt 1 ]]; then
  echo "ERROR: Use only one of: --template-nights, --observing-template-nights, or --template-reference"; exit 2;
fi
if [[ $TEMPLATE_METHODS -eq 0 ]]; then
  echo "ERROR: Must specify template nights using one of: --template-nights, --observing-template-nights, or --template-reference"; usage;
fi

SCIENCE_METHODS=0
[[ -n "$SCIENCE_NIGHTS_FILE" ]] && ((SCIENCE_METHODS++))
[[ -n "$OBS_SCIENCE_NIGHTS_FILE" ]] && ((SCIENCE_METHODS++))
[[ -n "$SCIENCE_REFERENCE_FILE" ]] && ((SCIENCE_METHODS++))
if [[ $SCIENCE_METHODS -gt 1 ]]; then
  echo "ERROR: Use only one of: --science-nights, --observing-science-nights, or --science-reference"; exit 2;
fi
if [[ $SCIENCE_METHODS -eq 0 ]]; then
  echo "ERROR: Must specify science nights using one of: --science-nights, --observing-science-nights, or --science-reference"; usage;
fi
[[ -n "$TEMPLATE_NIGHTS_FILE" && ! -f "$TEMPLATE_NIGHTS_FILE" ]] && { echo "Template nights file not found: $TEMPLATE_NIGHTS_FILE"; exit 2; }
[[ -n "$SCIENCE_NIGHTS_FILE" && ! -f "$SCIENCE_NIGHTS_FILE" ]] && { echo "Science nights file not found: $SCIENCE_NIGHTS_FILE"; exit 2; }
[[ -n "$OBS_TEMPLATE_NIGHTS_FILE" && ! -f "$OBS_TEMPLATE_NIGHTS_FILE" ]] && { echo "Observing-template nights file not found: $OBS_TEMPLATE_NIGHTS_FILE"; exit 2; }
[[ -n "$OBS_SCIENCE_NIGHTS_FILE" && ! -f "$OBS_SCIENCE_NIGHTS_FILE" ]] && { echo "Observing-science nights file not found: $OBS_SCIENCE_NIGHTS_FILE"; exit 2; }
[[ -n "$TEMPLATE_REFERENCE_FILE" && ! -f "$TEMPLATE_REFERENCE_FILE" ]] && { echo "Template reference file not found: $TEMPLATE_REFERENCE_FILE"; exit 2; }
[[ -n "$SCIENCE_REFERENCE_FILE" && ! -f "$SCIENCE_REFERENCE_FILE" ]] && { echo "Science reference file not found: $SCIENCE_REFERENCE_FILE"; exit 2; }

# Tract validation and auto-determination from RA/Dec
if [[ -n "$TRACT" && ( -n "$RA" || -n "$DEC" ) ]]; then
  echo "ERROR: Cannot specify both --tract and --ra/--dec (choose one method)"; exit 2;
fi
if [[ -n "$RA" && -z "$DEC" ]] || [[ -z "$RA" && -n "$DEC" ]]; then
  echo "ERROR: Must specify both --ra and --dec together"; exit 2;
fi
if [[ -z "$TRACT" && -z "$RA" ]]; then
  echo "ERROR: Must specify either --tract or --ra/--dec"; exit 2;
fi

# Auto-determine tract from RA/Dec will happen after bootstrap (needs repo to exist)
# For now, just validate that we have either tract or ra/dec specified
if [[ -z "$TRACT" && -z "$RA" ]]; then
  echo "ERROR: Must specify either --tract or --ra/--dec"; exit 2;
fi
if [[ -n "$RA" && -z "$DEC" ]] || [[ -z "$RA" && -n "$DEC" ]]; then
  echo "ERROR: Must specify both --ra and --dec together"; exit 2;
fi

# If tract was explicitly provided, validate it now
if [[ -n "$TRACT" ]] && ! [[ "$TRACT" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --tract must be numeric (got '$TRACT')"; exit 2;
fi
if [[ -n "$BAD_SUB_THRESH" && ! "$BAD_SUB_THRESH" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "ERROR: --bad-sub-threshold must be numeric"; exit 2;
fi
if [[ -z "${REPO:-}" ]]; then
  echo "ERROR: REPO is not set (check your .env)"; exit 2;
fi

# Forced photometry validation
if [[ "$FORCED_PHOT" == "true" ]]; then
  case "$FORCED_PHOT_IMAGE_TYPE" in
    visit|diffim|both) ;;
    *)
      echo "ERROR: --forced-phot-image-type must be visit, diffim, or both"; exit 2;
      ;;
  esac
  if [[ -n "$FORCED_PHOT_COORDS_FILE" && ! -f "$FORCED_PHOT_COORDS_FILE" ]]; then
    echo "ERROR: Forced phot coords file not found: $FORCED_PHOT_COORDS_FILE"; exit 2;
  fi
  if [[ -z "$FORCED_PHOT_COORDS_FILE" ]]; then
    [[ -z "$FORCED_PHOT_RA" ]] && FORCED_PHOT_RA="$RA"
    [[ -z "$FORCED_PHOT_DEC" ]] && FORCED_PHOT_DEC="$DEC"
    if [[ -z "$FORCED_PHOT_RA" || -z "$FORCED_PHOT_DEC" ]]; then
      echo "ERROR: --forced-phot requires RA/Dec (use --forced-phot-ra/--forced-phot-dec or --ra/--dec)"; exit 2;
    fi
  fi
fi

if [[ "$FORCED_PHOT_LIGHTCURVE" == "true" && "$FORCED_PHOT" != "true" ]]; then
  echo "ERROR: --forced-phot-lightcurve requires --forced-phot in this run"; exit 2;
fi

# Lightcurve validation (requires target coordinates)
if [[ "$LIGHTCURVE" == "true" || "$DIA_LIGHTCURVE_TASK" == "true" ]]; then
  if [[ -z "$RA" || -z "$DEC" ]]; then
    echo "ERROR: Lightcurve options require --ra and --dec for target coordinates"; exit 2;
  fi
fi

########################################
# Setup logging and RUN_ID
########################################
# Create RUN_ID for entire pipeline execution
export RUN_ID="dia_multiband_$(date -u +%Y%m%d_%H%M%S)_$$"

# Setup logging for orchestrator
setup_logging "other" "" "" "" "run_dia_multi_band"

# Redirect all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Multi-band DIA Pipeline"
log_info "RUN_ID: $RUN_ID"

########################################
# Helpers
########################################
# Note: log() function now provided by logging.sh (log_info)
run_or_dry() { if [[ "$DRY_RUN" == "true" ]]; then /bin/echo "[DRY-RUN] $*"; else log_info "Running: $*"; "$@"; fi; }

ensure_butler_available() {
  # Already present?
  if command -v butler >/dev/null 2>&1; then
    return 0
  fi

  # Explicit override
  if [[ -n "${BUTLER_BIN:-}" && -x "$BUTLER_BIN" ]]; then
    PATH="$(dirname "$BUTLER_BIN"):$PATH"
    export PATH
    if command -v butler >/dev/null 2>&1; then
      return 0
    fi
  fi

  # Preserve local package paths before conda activation can reset them
  local LOCAL_OBS_NICKEL_PY="${OBS_NICKEL}/python"
  local LOCAL_OBS_NICKEL_DATA_PY="${REPO_ROOT}/packages/obs_nickel_data/python"

  # Try to source LSST loader under STACK_DIR
  if [[ -n "${STACK_DIR:-}" ]]; then
    local loader=""
    for candidate in "loadLSST.bash" "loadLSST.sh" "loadLSST.zsh" "loadLSST.ash"; do
      if [[ -f "$STACK_DIR/$candidate" ]]; then
        loader="$STACK_DIR/$candidate"
        break
      fi
    done
    if [[ -n "$loader" ]]; then
      # shellcheck disable=SC1090
      source "$loader" >/dev/null 2>&1 || true
      if command -v setup >/dev/null 2>&1; then
        setup lsst_distrib >/dev/null 2>&1 || true
        # Set up local obs_nickel from repo (prefer over any globally installed version)
        if [[ -d "${OBS_NICKEL}/ups" ]]; then
          setup -r "$OBS_NICKEL" obs_nickel 2>/dev/null || setup obs_nickel 2>/dev/null || true
        else
          setup obs_nickel >/dev/null 2>&1 || true
        fi
        # Set up local obs_nickel_data from repo
        local OBS_NICKEL_DATA="${REPO_ROOT}/packages/obs_nickel_data"
        if [[ -d "${OBS_NICKEL_DATA}/ups" ]]; then
          setup -r "$OBS_NICKEL_DATA" obs_nickel_data 2>/dev/null || setup obs_nickel_data 2>/dev/null || true
        else
          setup obs_nickel_data >/dev/null 2>&1 || true
        fi
      fi
      # Re-export PYTHONPATH with local packages first (conda activation may have reset it)
      export PYTHONPATH="${LOCAL_OBS_NICKEL_PY}:${LOCAL_OBS_NICKEL_DATA_PY}:${PYTHONPATH:-}"
      if command -v butler >/dev/null 2>&1; then
        return 0
      fi
    fi
  fi

  # Common fallback installs
  # Use LSST_CONDA_ENV_NAME if set, otherwise fall back to common versions
  CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
  for candidate in \
    "/opt/anaconda3/envs/${CONDA_ENV}/bin/butler" \
    "/opt/rubin/envs/${CONDA_ENV}/bin/butler" \
    "/opt/lsst/software/stack/bin/butler"; do
    if [[ -x "$candidate" ]]; then
      PATH="$(dirname "$candidate"):$PATH"
      export PATH
      if command -v butler >/dev/null 2>&1; then
        return 0
      fi
    fi
  done

  echo "ERROR: 'butler' is not available. Set BUTLER_BIN to your butler executable or ensure the LSST stack is loaded (STACK_DIR=$STACK_DIR)." >&2
  return 1
}

# Convert observing-night list (local date) into UT day_obs list using helper script.
convert_observing_nights() {
  local obs_file="$1"
  local label="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  TEMP_FILES+=("$tmp_file")

  local converter_script="${REPO_ROOT:-}/scripts/utilities/observing_night_to_ut.sh"
  if [[ ! -x "$converter_script" ]]; then
    converter_script="./scripts/utilities/observing_night_to_ut.sh"
  fi
  if [[ ! -x "$converter_script" ]]; then
    echo "ERROR: observing-night conversion script not found: $converter_script"
    exit 2
  fi

  local cmd=("$converter_script" "$obs_file")
  [[ -n "$OBJECT_FILTER" ]] && cmd+=("--object" "$OBJECT_FILTER")
  [[ -n "$NIGHT_TIMEZONE" ]] && cmd+=("--timezone" "$NIGHT_TIMEZONE")

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] converting observing nights (${label}): ${cmd[*]}"
    cp "$obs_file" "$tmp_file"
  else
    if ! ensure_butler_available; then
      echo "ERROR: butler command not available. Cannot convert observing nights." >&2
      echo "       Try loading LSST stack: source \$STACK_DIR/loadLSST.bash && setup lsst_distrib" >&2
      return 1
    fi
    log "[convert] Observing nights (${label}) -> UT day_obs (timezone=${NIGHT_TIMEZONE:-unset})" >&2
    if ! "${cmd[@]}" > "$tmp_file" 2>&1; then
      echo "ERROR: Conversion failed for ${label} nights (file: ${obs_file})" >&2
      return 1
    fi
  fi

  echo "$tmp_file"
}

# Track temp files for cleanup
TEMP_FILES=()
cleanup_temp_files() {
  for f in "${TEMP_FILES[@]}"; do
    [[ -f "$f" ]] && rm -f "$f"
  done
}
trap cleanup_temp_files EXIT

read_nights() {
  local file="$1"
  local out=()
  while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | tr -d '[:space:]')"
    [[ -z "$line" ]] && continue
    out+=("$line")
  done < "$file"
  printf "%s\n" "${out[@]}"
}

# Parse YAML reference file and extract observing nights
# Input: $1 = YAML file path, $2 = optional band filter (e.g., "v")
# Output: Prints observing night values (one per line) to stdout
# Note: Observing nights are the keys under "nights:" section
parse_reference_yaml() {
  local yaml_file="$1"
  local band_filter="${2:-}"
  local tmp_file
  tmp_file="$(mktemp)"
  TEMP_FILES+=("$tmp_file")

  # Schema: nights → observing_night → filter → visits
  # Extract observing night values (numeric keys under "nights:")

  if [[ -n "$band_filter" ]]; then
    # Extract only nights that have data for the specified band
    # Look for numeric keys (observing nights) that have the filter
    awk -v band="$band_filter" '
      /^  [0-9]{8}:/ {
        current_night = substr($1, 1, length($1)-1)
        has_band = 0
      }
      /^    [a-z]:/ && current_night != "" {
        filter_name = substr($1, 1, length($1)-1)
        if (filter_name == band) {
          has_band = 1
        }
      }
      /^  [0-9]{8}:/ && current_night != "" && has_band {
        print current_night
        current_night = ""
        has_band = 0
      }
      END {
        if (current_night != "" && has_band) {
          print current_night
        }
      }
    ' "$yaml_file" | sort -u > "$tmp_file"
  else
    # Extract all observing nights (numeric keys at 2-space indent under "nights:")
    grep -E '^\s{2}[0-9]{8}:' "$yaml_file" | \
      awk '{gsub(/:/, "", $1); print $1}' | \
      sort -u > "$tmp_file"
  fi

  if [[ ! -s "$tmp_file" ]]; then
    # Empty nights file is OK when using PS1 templates (no template observations needed)
    # Return empty list rather than erroring
    return 0
  fi

  cat "$tmp_file"
}

uniq_list() { tr ' ' '\n' | sed '/^\s*$/d' | sort -u; }

# Check if a template collection exists and has template_coadd datasets
template_exists() {
  local tract="$1"
  local band="$2"
  local template_dir="$REPO/templates/deep/tract${tract}/${band}"

  # Check if template directory exists and has subdirectories (indicating runs)
  if [[ ! -d "$template_dir" ]]; then
    return 1
  fi

  # Check if there are any run subdirectories with template data
  if find "$template_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | grep -q .; then
    # Directory exists and has subdirectories - assume it has data
    return 0
  fi

  return 1
}

# Remove existing template runs/collections for a band when overwriting
purge_template_band() {
  local tract="$1"
  local band="$2"
  local template_parent="templates/deep/tract${tract}/${band}"
  local template_dir="$REPO/$template_parent"

  log "[band $band] Overwrite requested; removing existing template data: $template_parent"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] butler remove-collections \"$REPO\" \"$template_parent\" --purge-children"
    echo "[DRY-RUN] rm -rf \"$template_dir\""
    return 0
  fi

  # Remove collection chain (and child runs if supported)
  if ensure_butler_available; then
    butler remove-collections "$REPO" "$template_parent" --purge-children >/dev/null 2>&1 || \
      butler collection-chain "$REPO" "$template_parent" --mode=replace >/dev/null 2>&1 || true
  else
    log "[WARN] butler not available; skipping collection removal for $template_parent"
  fi

  rm -rf "$template_dir"
}

########################################
# Validate PS1 template options
########################################
if [[ "$USE_PS1_TEMPLATES" == "true" ]]; then
  # PS1 templates require RA/Dec for downloading
  if [[ -z "$RA" || -z "$DEC" ]]; then
    echo "ERROR: --use-ps1-templates requires --ra and --dec for downloading templates"
    exit 2
  fi
  # PS1 templates are incompatible with internal template building
  if [[ "$SKIP_TEMPLATE_BUILD" == "false" && "$AUTO_TEMPLATE" == "false" ]]; then
    echo "NOTE: --use-ps1-templates will skip internal template building"
    SKIP_TEMPLATE_BUILD=true
  fi
fi

# Function to check if PS1 template exists for a band
ps1_template_exists() {
  local band="$1"
  local ps1_collection="templates/ps1/${band}"

  if ! ensure_butler_available; then
    return 1
  fi

  # Check if collection exists and has template_coadd datasets
  if butler query-collections "$REPO" 2>/dev/null | grep -qx "$ps1_collection"; then
    local count=$(butler query-datasets "$REPO" template_coadd \
      --collections "$ps1_collection" 2>/dev/null | tail -n +3 | wc -l || echo "0")
    if [[ "$count" -gt 0 ]]; then
      return 0
    fi
  fi
  return 1
}

# Function to ingest PS1 template for a band
ingest_ps1_template() {
  local band="$1"
  local ra="$2"
  local dec="$3"

  log_info "Checking PS1 template for band $band..."

  if ps1_template_exists "$band"; then
    if [[ "$OVERWRITE_TEMPLATES" == "true" ]]; then
      log_info "  PS1 template exists for band $band; --overwrite-templates set, re-ingesting"
    else
      log_info "  PS1 template already exists for band $band"
      return 0
    fi
  fi

  log_info "  PS1 template not found, downloading and ingesting..."

  local ps1_script="$REPO_ROOT/scripts/pipeline/08_ingest_ps1_template.sh"
  if [[ ! -f "$ps1_script" ]]; then
    log_error "PS1 ingestion script not found: $ps1_script"
    return 1
  fi

  local ps1_args=(
    --ra "$ra"
    --dec "$dec"
    --band "$band"
    --collection "templates/ps1/${band}"
  )

  [[ -n "$TRACT" ]] && ps1_args+=(--tract "$TRACT")
  [[ -n "$PS1_DEGRADE_SEEING" ]] && ps1_args+=(--degrade-seeing "$PS1_DEGRADE_SEEING")
  [[ "$OVERWRITE_TEMPLATES" == "true" ]] && ps1_args+=(--overwrite)

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $ps1_script ${ps1_args[*]}"
    return 0
  fi

  if "$ps1_script" "${ps1_args[@]}"; then
    log_info "  Successfully ingested PS1 template for band $band"
    return 0
  else
    log_error "  Failed to ingest PS1 template for band $band"
    return 1
  fi
}

########################################
# Stage 0: Bootstrap if needed
########################################
if [[ "$OVERWRITE_TEMPLATES" == "true" ]]; then
  if [[ "$USE_PS1_TEMPLATES" == "true" ]]; then
    log "[INFO] --overwrite-templates will force PS1 template re-ingest"
  elif [[ "$SKIP_TEMPLATE_BUILD" == "true" || "$AUTO_TEMPLATE" == "true" ]]; then
    log "[WARN] --overwrite-templates specified but template build is disabled (skip-template-build/auto-template); flag will be ignored"
  fi
fi

if [[ ! -f "$REPO/butler.yaml" ]]; then
  if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
    echo "ERROR: Repo not found ($REPO) and --skip-bootstrap set"; exit 2;
  fi
  log "Repo not found ($REPO); running bootstrap (00_bootstrap_repo.sh)"
  run_or_dry ./scripts/pipeline/00_bootstrap_repo.sh
fi

########################################
# Auto-determine tract from RA/Dec (requires repo to exist)
########################################
if [[ -n "$RA" && -n "$DEC" ]] && [[ -z "$TRACT" ]]; then
  log "Auto-determining tract from RA=$RA, Dec=$DEC (skymap=$SKYMAP)"

  RADEC_SCRIPT="./scripts/utilities/radec_to_tract.py"
  if [[ ! -f "$RADEC_SCRIPT" ]]; then
    echo "ERROR: radec_to_tract.py not found at $RADEC_SCRIPT"; exit 2;
  fi

  # Use LSST Python to run the script
  # Must load LSST environment for Python imports to work
  if [[ -n "${STACK_DIR:-}" && -f "${STACK_DIR}/loadLSST.bash" ]]; then
    source "${STACK_DIR}/loadLSST.bash" >/dev/null 2>&1
    setup lsst_distrib >/dev/null 2>&1
    setup obs_nickel_data >/dev/null 2>&1 || true
  fi

  # Use LSST_CONDA_ENV_NAME if set, otherwise fall back to common version
  CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
  PYTHON_CMD="/opt/anaconda3/envs/${CONDA_ENV}/bin/python"
  if [[ ! -x "$PYTHON_CMD" ]]; then
    # Fallback to environment Python
    if [[ -n "${LSST_PYTHON:-}" && -x "$LSST_PYTHON" ]]; then
      PYTHON_CMD="$LSST_PYTHON"
    elif command -v python >/dev/null 2>&1; then
      PYTHON_CMD="python"
    else
      echo "ERROR: Python not found. Ensure LSST stack is loaded."; exit 2;
    fi
  fi

  TRACT=$($PYTHON_CMD "$RADEC_SCRIPT" "$RA" "$DEC" --skymap "$SKYMAP" --repo "$REPO" 2>&1)
  if [[ $? -ne 0 ]] || [[ -z "$TRACT" ]]; then
    echo "ERROR: Failed to determine tract from RA/Dec: $TRACT"; exit 2;
  fi
  log "Determined tract: $TRACT"

  # Validate determined tract
  if ! [[ "$TRACT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Determined tract is not numeric (got '$TRACT')"; exit 2;
  fi
fi

########################################
# Nights
########################################
# Handle template nights (choose one of three methods)
if [[ -n "$TEMPLATE_REFERENCE_FILE" ]]; then
  # Method 3: Parse YAML reference file
  log "[nights] Parsing template reference: $TEMPLATE_REFERENCE_FILE"
  TMP_TEMPLATE_FILE="$(mktemp)"
  TEMP_FILES+=("$TMP_TEMPLATE_FILE")
  if ! parse_reference_yaml "$TEMPLATE_REFERENCE_FILE" > "$TMP_TEMPLATE_FILE"; then
    echo "ERROR: Failed to parse template reference file: $TEMPLATE_REFERENCE_FILE"
    exit 2
  fi
  TEMPLATE_NIGHTS_FILE="$TMP_TEMPLATE_FILE"
  log "[nights] Extracted $(wc -l < "$TEMPLATE_NIGHTS_FILE" | tr -d ' ') template nights from reference"
elif [[ -n "$OBS_TEMPLATE_NIGHTS_FILE" ]]; then
  # Method 2: Convert observing nights to UT day_obs
  if ! TEMPLATE_NIGHTS_FILE="$(convert_observing_nights "$OBS_TEMPLATE_NIGHTS_FILE" "template")"; then
    echo "ERROR: Failed to convert observing template nights. Ensure LSST stack is loaded and butler is available."
    exit 2
  fi
  log "[nights] Converted observing template nights -> $TEMPLATE_NIGHTS_FILE (UTC day_obs)"
fi
# else: Method 1 - TEMPLATE_NIGHTS_FILE is already set

# Handle science nights (choose one of three methods)
if [[ -n "$SCIENCE_REFERENCE_FILE" ]]; then
  # Method 3: Parse YAML reference file
  log "[nights] Parsing science reference: $SCIENCE_REFERENCE_FILE"
  TMP_SCIENCE_FILE="$(mktemp)"
  TEMP_FILES+=("$TMP_SCIENCE_FILE")
  if ! parse_reference_yaml "$SCIENCE_REFERENCE_FILE" > "$TMP_SCIENCE_FILE"; then
    echo "ERROR: Failed to parse science reference file: $SCIENCE_REFERENCE_FILE"
    exit 2
  fi
  SCIENCE_NIGHTS_FILE="$TMP_SCIENCE_FILE"
  log "[nights] Extracted $(wc -l < "$SCIENCE_NIGHTS_FILE" | tr -d ' ') science nights from reference"
elif [[ -n "$OBS_SCIENCE_NIGHTS_FILE" ]]; then
  # Method 2: Convert observing nights to UT day_obs
  if ! SCIENCE_NIGHTS_FILE="$(convert_observing_nights "$OBS_SCIENCE_NIGHTS_FILE" "science")"; then
    echo "ERROR: Failed to convert observing science nights. Ensure LSST stack is loaded and butler is available."
    exit 2
  fi
  log "[nights] Converted observing science nights -> $SCIENCE_NIGHTS_FILE (UTC day_obs)"
fi
# else: Method 1 - SCIENCE_NIGHTS_FILE is already set

TEMPLATE_NIGHTS=($(read_nights "$TEMPLATE_NIGHTS_FILE"))
SCIENCE_NIGHTS=($(read_nights "$SCIENCE_NIGHTS_FILE"))
ALL_NIGHTS=($(printf "%s\n" "${TEMPLATE_NIGHTS[@]}" "${SCIENCE_NIGHTS[@]}" | uniq_list))

########################################
# Stage 0.5: Archive download (once per night)
########################################
if [[ "$SKIP_DOWNLOAD" == "true" ]]; then
  log "Skipping archive download (--skip-download)"
else
  for night in "${ALL_NIGHTS[@]}"; do
    DL_ARGS=(--night "$night")
    [[ "$DOWNLOAD_OVERWRITE" == "true" ]] && DL_ARGS+=(--overwrite)
    if ! run_or_dry ./scripts/pipeline/01_download_archive.sh "${DL_ARGS[@]}"; then
      log "[WARN] Archive download failed for night $night"
      FAILED_DOWNLOADS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
fi

########################################
# Stage 1: Calibs (once per night)
########################################
if [[ "$SKIP_CALIBS" == "true" ]]; then
  log "Skipping calibs (--skip-calibs)"
else
  for night in "${ALL_NIGHTS[@]}"; do
    if ! run_or_dry ./scripts/pipeline/10_calibs.sh --night "$night" --jobs "$JOBS"; then
      log "[WARN] Calibs failed for night $night"
      FAILED_CALIBS+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
fi

########################################
# Stage 2: Science (once per night)
########################################
if [[ "$SKIP_SCIENCE" == "true" ]]; then
  log "Skipping science (--skip-science)"
else
  for night in "${ALL_NIGHTS[@]}"; do
    SCI_ARGS=(--night "$night" -j "$JOBS" --skip-coadds)
    [[ -n "$OBJECT_FILTER" ]] && SCI_ARGS+=(--object "$OBJECT_FILTER")
    [[ -n "$SCIENCE_CONFIG" ]] && SCI_ARGS+=(--science-config "$SCIENCE_CONFIG")
    if ! run_or_dry ./scripts/pipeline/20_science.sh "${SCI_ARGS[@]}"; then
      log "[WARN] Science failed for night $night"
      FAILED_SCIENCE+=("$night")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
fi

########################################
# Stage 3/4: Per-band template + DIA
########################################
IFS=',' read -r -a BAND_ARRAY <<< "$BANDS"

for BAND in "${BAND_ARRAY[@]}"; do
  BAND="$(echo "$BAND" | tr -d '[:space:]')"
  [[ -z "$BAND" ]] && continue
  log "=== Band: $BAND ==="

  TEMPLATE_COLLECTION=""
  TEMPLATE_PARENT="templates/deep/tract${TRACT}/${BAND}"
  TEMPLATE_DIR="$REPO/$TEMPLATE_PARENT"

  # Stage 2.5: PS1 template ingestion (if requested)
  if [[ "$USE_PS1_TEMPLATES" == "true" ]]; then
    log_section "PS1 Template for band $BAND"
    if ! ingest_ps1_template "$BAND" "$RA" "$DEC"; then
      log "[WARN] PS1 template ingestion failed for band $BAND"
      FAILED_TEMPLATE+=("ps1/$BAND")
      EXIT_CODE=1
      if [[ "$CONTINUE_ON_ERROR" == "false" ]]; then
        echo "ERROR: PS1 template ingestion failed. Use --continue-on-error to proceed anyway."
        exit 2
      fi
      # Continue with next band if error handling allows
      continue
    fi
    # Set template collection to PS1
    TEMPLATE_COLLECTION="templates/ps1/${BAND}"
    log_info "Using PS1 template: $TEMPLATE_COLLECTION"
  elif [[ "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "false" ]]; then
    if [[ "$OVERWRITE_TEMPLATES" == "true" ]]; then
      purge_template_band "$TRACT" "$BAND"
    fi

    if [[ "$OVERWRITE_TEMPLATES" == "false" ]] && template_exists "$TRACT" "$BAND"; then
      TEMPLATE_COLLECTION="$TEMPLATE_PARENT"
      log "[band $BAND] Template already exists: $TEMPLATE_COLLECTION (skipping rebuild; use --overwrite-templates to force)"
    else
      # Build new template
      TMP_NIGHTS_FILE="$(mktemp)"
      TEMP_FILES+=("$TMP_NIGHTS_FILE")
      printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TMP_NIGHTS_FILE"
      COADD_CMD=(./scripts/pipeline/30_coadds.sh --nights-file "$TMP_NIGHTS_FILE" --band "$BAND" --tract "$TRACT" -j "$JOBS")
      [[ "$OVERWRITE_TEMPLATES" == "true" ]] && COADD_CMD+=(--rebase)
      if ! run_or_dry "${COADD_CMD[@]}"; then
        log "[WARN] Template build failed for band $BAND"
        FAILED_TEMPLATE+=("$BAND")
        EXIT_CODE=1
        [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
        continue
      fi

      # Use the parent collection (CHAINED collection that points to latest run)
      # The 30_coadds.sh script creates both:
      #   - templates/deep/tract1825/i/TIMESTAMP (RUN collection)
      #   - templates/deep/tract1825/i (CHAINED collection pointing to the run)
      TEMPLATE_COLLECTION="$TEMPLATE_PARENT"

      # Verify it exists by checking the filesystem (faster than butler query)
      if [[ ! -d "$TEMPLATE_DIR" ]]; then
        log "[WARN] Template directory not found: $TEMPLATE_DIR"
        log "[WARN] Checking for run collections..."

        # Fallback: try to find any run collection for this tract/band
        TEMPLATE_RUN=$(find "$REPO/templates/deep/tract${TRACT}/${BAND}" -maxdepth 1 -type d -name "20*" 2>/dev/null | sort | tail -n1)
        if [[ -n "$TEMPLATE_RUN" ]]; then
          TEMPLATE_COLLECTION=$(basename "$TEMPLATE_RUN")
          TEMPLATE_COLLECTION="templates/deep/tract${TRACT}/${BAND}/${TEMPLATE_COLLECTION}"
          log "[band $BAND] Found run collection: $TEMPLATE_COLLECTION"
        else
          echo "ERROR: No template found for band $BAND, tract $TRACT"
          echo "       Expected directory: $TEMPLATE_DIR"
          echo "       This shouldn't happen if 30_coadds.sh succeeded"
          exit 2
        fi
      else
        log "[band $BAND] Using template: $TEMPLATE_COLLECTION"
      fi
    fi
  fi

  for night in "${SCIENCE_NIGHTS[@]}"; do
    if [[ "$SKIP_DIA" == "true" ]]; then
      log_info "[band $BAND] Skipping DIA for night $night (--skip-dia)"
    else
      DIA_ARGS=(--night "$night" -j "$JOBS" --band "$BAND" --tract "$TRACT")
      [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
      if [[ -n "$TEMPLATE_COLLECTION" ]]; then
        DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
      else
        # Use auto-template if no specific template collection was built
        DIA_ARGS+=(--auto-template)
        # Prefer PS1 templates if that's what we're using
        [[ "$USE_PS1_TEMPLATES" == "true" ]] && DIA_ARGS+=(--prefer-ps1)
      fi
      if [[ -n "$BAD_SUB_THRESH" ]]; then
        DIA_ARGS+=(--bad-sub-threshold "$BAD_SUB_THRESH")
      fi
      if [[ "$DIA_ANALYSIS" == "true" ]]; then
        DIA_ARGS+=(--analysis)
      fi
      if ! run_or_dry ./scripts/pipeline/40_diff_imaging.sh "${DIA_ARGS[@]}"; then
        log "[WARN] DIA failed for night $night band $BAND"
        FAILED_DIA+=("${night}/${BAND}")
        EXIT_CODE=1
        [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
      fi
    fi

    if [[ "$FORCED_PHOT" == "true" ]]; then
      FP_ARGS=(--night "$night" --run-id "$RUN_ID" --image-type "$FORCED_PHOT_IMAGE_TYPE" --band "$BAND")
      if [[ -n "$FORCED_PHOT_COORDS_FILE" ]]; then
        FP_ARGS+=(--coords-file "$FORCED_PHOT_COORDS_FILE")
      else
        FP_ARGS+=(--ra "$FORCED_PHOT_RA" --dec "$FORCED_PHOT_DEC")
      fi

      if ! run_or_dry ./scripts/pipeline/46_forced_photometry_radec.sh "${FP_ARGS[@]}"; then
        log "[WARN] Forced photometry failed for night $night band $BAND"
        FAILED_FORCED_PHOT+=("${night}/${BAND}")
        EXIT_CODE=1
        [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
      fi
    fi
done
done

########################################
# Stage 5: Forced photometry lightcurve task (PipelineTask)
########################################

if [[ "$FORCED_PHOT_LIGHTCURVE" == "true" ]]; then
  log_section "Forced Photometry Lightcurve Task"

  if ! ensure_butler_available; then
    log_warn "butler command not available; skipping forced phot lightcurve task"
  elif ! command -v pipetask >/dev/null 2>&1; then
    log_warn "pipetask command not available; skipping forced phot lightcurve task"
  else
    PROCESSCCD_COLLECTIONS=()
    FORCED_PHOT_COLLECTIONS=()
    HAS_VISIT=false
    HAS_DIFFIM=false

    for night in "${SCIENCE_NIGHTS[@]}"; do
      PROCESSCCD_COLL="$(butler query-collections "$REPO" "Nickel/runs/${night}/processCcd/*/run" 2>/dev/null | \
        tail -n +3 | awk '{print $1}' | sort | tail -n 1)"
      if [[ -n "$PROCESSCCD_COLL" ]]; then
        PROCESSCCD_COLLECTIONS+=("$PROCESSCCD_COLL")
      else
        log_warn "No processCcd collections found for night $night"
      fi

      if [[ "$FORCED_PHOT_IMAGE_TYPE" == "visit" || "$FORCED_PHOT_IMAGE_TYPE" == "both" ]]; then
        VISIT_COLL="Nickel/runs/${night}/forcedPhotRaDec/${RUN_ID}/visit"
        if butler query-collections "$REPO" "$VISIT_COLL" 2>/dev/null | tail -n +3 | awk '{print $1}' | grep -q .; then
          FORCED_PHOT_COLLECTIONS+=("$VISIT_COLL")
          HAS_VISIT=true
        else
          log_warn "Forced phot visit collection not found: $VISIT_COLL"
        fi
      fi

      if [[ "$FORCED_PHOT_IMAGE_TYPE" == "diffim" || "$FORCED_PHOT_IMAGE_TYPE" == "both" ]]; then
        DIFFIM_COLL="Nickel/runs/${night}/forcedPhotRaDec/${RUN_ID}/diffim"
        if butler query-collections "$REPO" "$DIFFIM_COLL" 2>/dev/null | tail -n +3 | awk '{print $1}' | grep -q .; then
          FORCED_PHOT_COLLECTIONS+=("$DIFFIM_COLL")
          HAS_DIFFIM=true
        else
          log_warn "Forced phot diffim collection not found: $DIFFIM_COLL"
        fi
      fi
    done

    PROCESSCCD_COLLECTIONS_CSV="$(printf "%s\n" "${PROCESSCCD_COLLECTIONS[@]}" | sort -u | paste -sd, -)"
    FORCED_PHOT_COLLECTIONS_CSV="$(printf "%s\n" "${FORCED_PHOT_COLLECTIONS[@]}" | sort -u | paste -sd, -)"

    if [[ -z "$PROCESSCCD_COLLECTIONS_CSV" ]]; then
      log_warn "Missing processCcd collections; skipping forced phot lightcurve task"
    elif [[ -z "$FORCED_PHOT_COLLECTIONS_CSV" ]]; then
      log_warn "No forced phot collections found; skipping forced phot lightcurve task"
    else
      INPUT_COLLECTIONS="${PROCESSCCD_COLLECTIONS_CSV},${FORCED_PHOT_COLLECTIONS_CSV}"
      FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION="Nickel/runs/forcedPhotLightcurve/${RUN_ID}"
      FORCED_PHOT_LIGHTCURVE_OUTPUT_RUN="${FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION}/run"

      LC_LABEL="$LIGHTCURVE_NAME"
      if [[ -z "$LC_LABEL" ]]; then
        if [[ -n "$OBJECT_FILTER" ]]; then
          LC_LABEL="$OBJECT_FILTER"
        elif [[ -n "$RA" && -n "$DEC" ]]; then
          LC_LABEL="RA=${RA}, Dec=${DEC}"
        fi
      fi

      LIGHTCURVE_SUBSET=""
      if [[ "$HAS_VISIT" == "true" && "$HAS_DIFFIM" == "true" ]]; then
        LIGHTCURVE_SUBSET="all-lightcurves"
      elif [[ "$HAS_VISIT" == "true" ]]; then
        LIGHTCURVE_SUBSET="visit-lightcurve"
      elif [[ "$HAS_DIFFIM" == "true" ]]; then
        LIGHTCURVE_SUBSET="diffim-lightcurve"
      fi

      if [[ -z "$LIGHTCURVE_SUBSET" ]]; then
        log_warn "No forced phot collections available for lightcurve task; skipping"
      else
        DATA_QUERY="instrument='Nickel'"

        PIPETASK_ARGS=(
          pipetask run
          --butler-config "$REPO"
          --input "$INPUT_COLLECTIONS"
          --output "$FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION"
          --output-run "$FORCED_PHOT_LIGHTCURVE_OUTPUT_RUN"
          --register-dataset-types
          --pipeline "$OBS_NICKEL/pipelines/ForcedPhotRaDec.yaml#${LIGHTCURVE_SUBSET}"
          --data-query "$DATA_QUERY"
        )

        if [[ -n "$LC_LABEL" ]]; then
          if [[ "$LIGHTCURVE_SUBSET" == "visit-lightcurve" ]]; then
            PIPETASK_ARGS+=(-c "forcedPhotLightcurve:targetName=${LC_LABEL}")
          elif [[ "$LIGHTCURVE_SUBSET" == "diffim-lightcurve" ]]; then
            PIPETASK_ARGS+=(-c "forcedPhotDiffimLightcurve:targetName=${LC_LABEL}")
          else
            PIPETASK_ARGS+=(
              -c "forcedPhotLightcurve:targetName=${LC_LABEL}"
              -c "forcedPhotDiffimLightcurve:targetName=${LC_LABEL}"
            )
          fi
        fi

        if ! run_or_dry "${PIPETASK_ARGS[@]}"; then
          log_warn "Forced phot lightcurve task failed"
          FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION=""
        else
          log_info "Forced phot lightcurve outputs: $FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION"
        fi
      fi
    fi
  fi
fi

########################################
# Stage 6: DIA lightcurve task (PipelineTask)
########################################
DIA_LIGHTCURVE_OUTPUT_COLLECTION=""

if [[ "$DIA_LIGHTCURVE_TASK" == "true" ]]; then
  log_section "DIA Lightcurve Task"

  if ! ensure_butler_available; then
    log_warn "butler command not available; skipping DIA lightcurve task"
  elif ! command -v pipetask >/dev/null 2>&1; then
    log_warn "pipetask command not available; skipping DIA lightcurve task"
  else
    PROCESSCCD_COLLECTIONS=()
    DIFF_COLLECTIONS=()

    for night in "${SCIENCE_NIGHTS[@]}"; do
      PROCESSCCD_COLL="$(butler query-collections "$REPO" "Nickel/runs/${night}/processCcd/*/run" 2>/dev/null | \
        tail -n +3 | awk '{print $1}' | sort | tail -n 1)"
      if [[ -n "$PROCESSCCD_COLL" ]]; then
        PROCESSCCD_COLLECTIONS+=("$PROCESSCCD_COLL")
      else
        log_warn "No processCcd collections found for night $night"
      fi

      while read -r diff_coll; do
        [[ -n "$diff_coll" ]] && DIFF_COLLECTIONS+=("$diff_coll")
      done < <(butler query-collections "$REPO" "Nickel/runs/${night}/diff/*/run" 2>/dev/null | \
        tail -n +3 | awk '{print $1}')
    done

    PROCESSCCD_COLLECTIONS_CSV="$(printf "%s\n" "${PROCESSCCD_COLLECTIONS[@]}" | sort -u | paste -sd, -)"
    DIFF_COLLECTIONS_CSV="$(printf "%s\n" "${DIFF_COLLECTIONS[@]}" | sort -r | uniq | paste -sd, -)"

    if [[ -z "$PROCESSCCD_COLLECTIONS_CSV" || -z "$DIFF_COLLECTIONS_CSV" ]]; then
      log_warn "Missing input collections for DIA lightcurve task; skipping"
    else
      INPUT_COLLECTIONS="${PROCESSCCD_COLLECTIONS_CSV},${DIFF_COLLECTIONS_CSV}"
      DIA_LIGHTCURVE_OUTPUT_COLLECTION="Nickel/runs/diaLightcurve/${RUN_ID}"
      DIA_LIGHTCURVE_OUTPUT_RUN="${DIA_LIGHTCURVE_OUTPUT_COLLECTION}/run"

      LC_LABEL="$LIGHTCURVE_NAME"
      if [[ -z "$LC_LABEL" ]]; then
        if [[ -n "$OBJECT_FILTER" ]]; then
          LC_LABEL="$OBJECT_FILTER"
        else
          LC_LABEL="RA=${RA}, Dec=${DEC}"
        fi
      fi

      DATA_QUERY="instrument='Nickel'"
      if [[ -n "$LIGHTCURVE_BAND" ]]; then
        DATA_QUERY="${DATA_QUERY} AND band='${LIGHTCURVE_BAND}'"
      fi

      PIPETASK_ARGS=(
        pipetask run
        --butler-config "$REPO"
        --input "$INPUT_COLLECTIONS"
        --output "$DIA_LIGHTCURVE_OUTPUT_COLLECTION"
        --output-run "$DIA_LIGHTCURVE_OUTPUT_RUN"
        --register-dataset-types
        --pipeline "$OBS_NICKEL/pipelines/DIA.yaml#dia-lightcurve"
        --data-query "$DATA_QUERY"
        -c "plotDiaLightcurve:ra=$RA"
        -c "plotDiaLightcurve:dec=$DEC"
        -c "plotDiaLightcurve:radiusArcsec=$LIGHTCURVE_RADIUS"
        -c "plotDiaLightcurve:minSnr=$LIGHTCURVE_MIN_SNR"
      )
      [[ -n "$LC_LABEL" ]] && PIPETASK_ARGS+=(-c "plotDiaLightcurve:targetName=${LC_LABEL}")

      if ! run_or_dry "${PIPETASK_ARGS[@]}"; then
        log_warn "DIA lightcurve task failed"
        DIA_LIGHTCURVE_OUTPUT_COLLECTION=""
      else
        log_info "DIA lightcurve outputs: $DIA_LIGHTCURVE_OUTPUT_COLLECTION"
      fi
    fi
  fi
fi

########################################
# Stage 7: Lightcurve analysis (CLI)
########################################
LIGHTCURVE_OUTPUT=""
LIGHTCURVE_PLOT=""

if [[ "$LIGHTCURVE" == "true" ]]; then
  log_section "Lightcurve Extraction"

  if ! ensure_butler_available; then
    log_warn "butler command not available; skipping lightcurve extraction"
  else
    LC_DIR="${LIGHTCURVE_OUTPUT_DIR:-$RUN_LOG_DIR/lightcurve}"
    mkdir -p "$LC_DIR"

    LC_LABEL="$LIGHTCURVE_NAME"
    if [[ -z "$LC_LABEL" ]]; then
      if [[ -n "$OBJECT_FILTER" ]]; then
        LC_LABEL="$OBJECT_FILTER"
      else
        LC_LABEL="ra${RA}_dec${DEC}"
      fi
    fi
    LC_LABEL_SAFE="$(echo "$LC_LABEL" | tr ' /' '_' | tr -cd '[:alnum:]_.-')"
    LIGHTCURVE_OUTPUT="$LC_DIR/${LC_LABEL_SAFE}_lightcurve.csv"

    DIA_COLLECTIONS=()
    for night in "${SCIENCE_NIGHTS[@]}"; do
      while read -r coll; do
        [[ -n "$coll" ]] && DIA_COLLECTIONS+=("$coll")
      done < <(butler query-collections "$REPO" "Nickel/runs/${night}/diff/*/run" 2>/dev/null | \
        tail -n +3 | awk '{print $1}')
    done

    if [[ ${#DIA_COLLECTIONS[@]} -eq 0 ]]; then
      log_warn "No DIA collections found; skipping lightcurve extraction"
    else
      DIA_COLLECTIONS_CSV="$(printf "%s\n" "${DIA_COLLECTIONS[@]}" | sort -u | paste -sd, -)"

      LC_CMD="$(command -v obsn-dia-lightcurve || true)"
      if [[ -z "$LC_CMD" ]]; then
        log_warn "obsn-dia-lightcurve not found; skipping lightcurve extraction"
      else
        LC_ARGS=(
          --repo "$REPO"
          --collection "$DIA_COLLECTIONS_CSV"
          --ra "$RA"
          --dec "$DEC"
          --radius "$LIGHTCURVE_RADIUS"
          --min-snr "$LIGHTCURVE_MIN_SNR"
          --dataset-type "$LIGHTCURVE_DATASET_TYPE"
          --output "$LIGHTCURVE_OUTPUT"
          --plot
          --name "$LC_LABEL"
        )
        [[ -n "$LIGHTCURVE_BAND" ]] && LC_ARGS+=(--band "$LIGHTCURVE_BAND")

        if ! run_or_dry "$LC_CMD" "${LC_ARGS[@]}"; then
          log_warn "Lightcurve extraction failed (may be no detections)"
        fi

        if [[ -f "$LIGHTCURVE_OUTPUT" ]]; then
          LIGHTCURVE_PLOT="${LIGHTCURVE_OUTPUT%.csv}.png"
          log_info "Lightcurve saved: $LIGHTCURVE_OUTPUT"
          [[ -f "$LIGHTCURVE_PLOT" ]] && log_info "Lightcurve plot: $LIGHTCURVE_PLOT"
        fi
      fi
    fi
  fi
fi

log_section "Pipeline Complete"
log_info "All bands complete"

# Write summary
SUMMARY_TEXT="$(cat <<EOF
Multi-band DIA Pipeline Summary
================================

RUN_ID: $RUN_ID
Bands: $BANDS
Total nights: ${#SCIENCE_NIGHTS[@]}

Results:
$(if [[ ${#FAILED_DOWNLOADS[@]} -gt 0 ]]; then echo "  Failed downloads: ${FAILED_DOWNLOADS[*]}"; else echo "  All downloads succeeded (or skipped)"; fi)
$(if [[ ${#FAILED_CALIBS[@]} -gt 0 ]]; then echo "  Failed calibs: ${FAILED_CALIBS[*]}"; else echo "  All calibs succeeded"; fi)
$(if [[ ${#FAILED_SCIENCE[@]} -gt 0 ]]; then echo "  Failed science: ${FAILED_SCIENCE[*]}"; else echo "  All science succeeded"; fi)
$(if [[ ${#FAILED_TEMPLATE[@]} -gt 0 ]]; then echo "  Failed templates: ${FAILED_TEMPLATE[*]}"; else echo "  All templates succeeded"; fi)
$(if [[ ${#FAILED_DIA[@]} -gt 0 ]]; then echo "  Failed DIA: ${FAILED_DIA[*]}"; else echo "  All DIA succeeded"; fi)
$(if [[ "$DIA_ANALYSIS" == "true" ]]; then echo "  DIA analysis: enabled"; else echo "  DIA analysis: disabled"; fi)
$(if [[ "$DIA_LIGHTCURVE_TASK" == "true" ]]; then if [[ -n "$DIA_LIGHTCURVE_OUTPUT_COLLECTION" ]]; then echo "  DIA lightcurve task: $DIA_LIGHTCURVE_OUTPUT_COLLECTION"; else echo "  DIA lightcurve task: not generated"; fi; else echo "  DIA lightcurve task: skipped"; fi)
$(if [[ "$FORCED_PHOT_LIGHTCURVE" == "true" ]]; then if [[ -n "$FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION" ]]; then echo "  Forced phot lightcurve: $FORCED_PHOT_LIGHTCURVE_OUTPUT_COLLECTION"; else echo "  Forced phot lightcurve: not generated"; fi; else echo "  Forced phot lightcurve: skipped"; fi)
$(if [[ ${#FAILED_FORCED_PHOT[@]} -gt 0 ]]; then echo "  Failed forced phot: ${FAILED_FORCED_PHOT[*]}"; elif [[ "$FORCED_PHOT" == "true" ]]; then echo "  Forced phot completed"; else echo "  Forced phot skipped"; fi)
$(if [[ "$LIGHTCURVE" == "true" ]]; then if [[ -n "$LIGHTCURVE_OUTPUT" && -f "$LIGHTCURVE_OUTPUT" ]]; then echo "  Lightcurve: $LIGHTCURVE_OUTPUT"; else echo "  Lightcurve: not generated"; fi; else echo "  Lightcurve: skipped"; fi)

Exit code: $EXIT_CODE
EOF
)"

write_summary "$SUMMARY_TEXT"

if [[ "$CONTINUE_ON_ERROR" == "true" ]]; then
  [[ ${#FAILED_DOWNLOADS[@]} -gt 0 ]] && log_warn "Failed downloads: ${FAILED_DOWNLOADS[*]}"
  [[ ${#FAILED_CALIBS[@]} -gt 0 ]] && log_warn "Failed calibs: ${FAILED_CALIBS[*]}"
  [[ ${#FAILED_SCIENCE[@]} -gt 0 ]] && log_warn "Failed science: ${FAILED_SCIENCE[*]}"
  [[ ${#FAILED_TEMPLATE[@]} -gt 0 ]] && log_warn "Failed template builds: ${FAILED_TEMPLATE[*]}"
  [[ ${#FAILED_DIA[@]} -gt 0 ]] && log_warn "Failed DIA: ${FAILED_DIA[*]}"
  [[ ${#FAILED_FORCED_PHOT[@]} -gt 0 ]] && log_warn "Failed forced phot: ${FAILED_FORCED_PHOT[*]}"
fi

# Print final log summary
print_log_summary

exit $EXIT_CODE
