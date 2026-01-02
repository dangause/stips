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
SKIP_DOWNLOAD=false
DOWNLOAD_OVERWRITE=false
SKIP_TEMPLATE_BUILD=false
AUTO_TEMPLATE=false
DRY_RUN=false
CONTINUE_ON_ERROR=false
SKIP_BOOTSTRAP=false
SKIP_CALIBS=false
SKIP_SCIENCE=false

# Exit codes: 0=success, 1=failures with --continue-on-error, 2=fatal error
EXIT_CODE=0
FAILED_DOWNLOADS=()
FAILED_CALIBS=()
FAILED_SCIENCE=()
FAILED_TEMPLATE=()
FAILED_DIA=()

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
  --jobs N                 Parallel jobs for pipeline tasks (default: ${JOBS})
  --bad-sub-threshold X    Override badSubtractionRatioThreshold for DIA
  --skip-download          Skip archive downloads (assumes raw data already present)
  --download-overwrite     Re-download even if files exist (passes --overwrite)

Template Options:
  --skip-template-build    Skip 30_coadds (use existing templates)
  --auto-template          Let 40_diff_imaging auto-discover templates (skips 30)

Pipeline Control:
  --skip-bootstrap         Skip repository bootstrap (fail if repo doesn't exist)
  --skip-calibs            Skip calibration processing (10_calibs.sh)
  --skip-science           Skip science processing (20_science.sh)
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
    --jobs|-j)         JOBS="${2:-4}"; shift; shift;;
    --bad-sub-threshold) BAD_SUB_THRESH="${2:-}"; shift; shift;;
    --skip-download)   SKIP_DOWNLOAD=true; shift;;
    --download-overwrite) DOWNLOAD_OVERWRITE=true; shift;;
    --skip-template-build) SKIP_TEMPLATE_BUILD=true; shift;;
    --auto-template)   AUTO_TEMPLATE=true; shift;;
    --dry-run)         DRY_RUN=true; shift;;
    --continue-on-error) CONTINUE_ON_ERROR=true; shift;;
    --skip-bootstrap)  SKIP_BOOTSTRAP=true; shift;;
    --skip-calibs)     SKIP_CALIBS=true; shift;;
    --skip-science)    SKIP_SCIENCE=true; shift;;
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
        setup obs_nickel >/dev/null 2>&1 || true
      fi
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

  local converter_script="${OBS_NICKEL:-}/scripts/utilities/observing_night_to_ut.sh"
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
    echo "ERROR: No valid observing nights found in reference file: $yaml_file" >&2
    [[ -n "$band_filter" ]] && echo "       (filter: $band_filter)" >&2
    return 1
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

########################################
# Stage 0: Bootstrap if needed
########################################
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

  if [[ "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "false" ]]; then
    # Check if template already exists with data
    TEMPLATE_DIR="$REPO/templates/deep/tract${TRACT}/${BAND}"
    if [[ -d "$TEMPLATE_DIR" ]] && find "$TEMPLATE_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | grep -q .; then
      TEMPLATE_COLLECTION="templates/deep/tract${TRACT}/${BAND}"
      log "[band $BAND] Template already exists: $TEMPLATE_COLLECTION (skipping rebuild)"
    else
      # Build new template
      TMP_NIGHTS_FILE="$(mktemp)"
      TEMP_FILES+=("$TMP_NIGHTS_FILE")
      printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TMP_NIGHTS_FILE"
      if ! run_or_dry ./scripts/pipeline/30_coadds.sh --nights-file "$TMP_NIGHTS_FILE" --band "$BAND" --tract "$TRACT" -j "$JOBS"; then
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
      TEMPLATE_COLLECTION="templates/deep/tract${TRACT}/${BAND}"

      # Verify it exists by checking the filesystem (faster than butler query)
      TEMPLATE_DIR="$REPO/templates/deep/tract${TRACT}/${BAND}"
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
    DIA_ARGS=(--night "$night" -j "$JOBS" --band "$BAND" --tract "$TRACT")
    [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
    if [[ -n "$TEMPLATE_COLLECTION" ]]; then
      DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
    else
      # Use auto-template if no specific template collection was built
      DIA_ARGS+=(--auto-template)
    fi
    if [[ -n "$BAD_SUB_THRESH" ]]; then
      DIA_ARGS+=(--bad-sub-threshold "$BAD_SUB_THRESH")
    fi
    if ! run_or_dry ./scripts/pipeline/40_diff_imaging.sh "${DIA_ARGS[@]}"; then
      log "[WARN] DIA failed for night $night band $BAND"
      FAILED_DIA+=("${night}/${BAND}")
      EXIT_CODE=1
      [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit 2
    fi
  done
done

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
fi

# Print final log summary
print_log_summary

exit $EXIT_CODE
