#!/usr/bin/env bash
# batch_process_nights.sh — Process multiple nights through calibs → science → coadds → DIA
#
# Usage:
#   batch_process_nights.sh --nights-file nights.txt [options]
#   batch_process_nights.sh --nights "20240625,20240626,20240627" [options]
#
# This script processes each night sequentially through:
#   1. 10_calibs.sh  (bias, flats, defects)
#   2. 20_science.sh (ISR, calibrateImage, single-visit processing)
#   3. 30_coadds.sh  (optional multi-night coadd at the end)
#   4. 40_diff_imaging.sh (optional difference imaging for transients)

# set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

########## CLI ##########
NIGHTS_FILE=""
NIGHTS_LIST=""
JOBS="${JOBS:-8}"
SKIP_DOWNLOAD=false
SKIP_CALIBS=false
SKIP_SCIENCE=false
SKIP_COADDS=false
RUN_DIA=false
DIA_AUTO_TEMPLATE=false
DIA_TEMPLATE=""
DIA_EXCLUDE_START=""
DIA_EXCLUDE_END=""
BUILD_TEMPLATE=false
TEMPLATE_TRACT=""
TEMPLATE_BAND=""
TEMPLATE_PATCH=""
OBJECT_FILTER=""
BAD_EXPOSURES_FILE=""
DRY_RUN=false
CONTINUE_ON_ERROR=false
LOG_DIR="$OBS_NICKEL/logs/batch"
DOWNLOAD_OVERWRITE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nights-file)
      NIGHTS_FILE="${2:-}"
      shift 2
      ;;
    --nights)
      NIGHTS_LIST="${2:-}"
      shift 2
      ;;
    -j|--jobs)
      JOBS="${2:-}"
      shift 2
      ;;
    --skip-download)
      SKIP_DOWNLOAD=true
      shift 1
      ;;
    --download-overwrite)
      DOWNLOAD_OVERWRITE=true
      shift 1
      ;;
    --skip-calibs)
      SKIP_CALIBS=true
      shift 1
      ;;
    --skip-science)
      SKIP_SCIENCE=true
      shift 1
      ;;
    --skip-coadds)
      SKIP_COADDS=true
      shift 1
      ;;
    --run-dia)
      RUN_DIA=true
      shift 1
      ;;
    --dia-auto-template)
      DIA_AUTO_TEMPLATE=true
      shift 1
      ;;
    --dia-template)
      DIA_TEMPLATE="${2:-}"
      shift 2
      ;;
    --dia-exclude-start)
      DIA_EXCLUDE_START="${2:-}"
      shift 2
      ;;
    --dia-exclude-end)
      DIA_EXCLUDE_END="${2:-}"
      shift 2
      ;;
    --build-template)
      BUILD_TEMPLATE=true
      shift 1
      ;;
    --template-tract)
      TEMPLATE_TRACT="${2:-}"
      shift 2
      ;;
    --template-band)
      TEMPLATE_BAND="${2:-}"
      shift 2
      ;;
    --template-patch)
      TEMPLATE_PATCH="${2:-}"
      shift 2
      ;;
    --object)
      OBJECT_FILTER="${2:-}"
      shift 2
      ;;
    --bad-file)
      BAD_EXPOSURES_FILE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift 1
      ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=true
      shift 1
      ;;
    --log-dir)
      LOG_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage: $0 --nights-file FILE [options]
       $0 --nights "YYYYMMDD,YYYYMMDD,..." [options]

Process multiple nights through the full pipeline (calibs → science → coadds).

Required (one of):
  --nights-file FILE        File with list of nights (YYYYMMDD, one per line)
  --nights NIGHTS           Comma-separated list of nights

Options:
  -j, --jobs N              Parallel jobs for pipetask (default: ${JOBS})
  --skip-download           Skip downloading from archive (assume data exists)
  --download-overwrite      Re-download files even if they exist
  --skip-calibs             Skip calibration processing (10_calibs.sh)
  --skip-science            Skip science processing (20_science.sh)
  --skip-coadds             Skip per-night coadds in 20_science.sh
  --object NAME             Filter science exposures by OBJECT header
  --bad-file FILE           File with bad exposure/visit IDs to exclude
  --dry-run                 Print commands without executing
  --continue-on-error       Continue processing remaining nights if one fails
  --log-dir DIR             Directory for batch logs (default: logs/batch)

Difference Imaging (DIA):
  --run-dia                 Run difference imaging (40_diff_imaging.sh) after science
  --dia-auto-template       Auto-discover best template for DIA (recommended)
  --dia-template COLL       Use specific template collection for DIA
  --dia-exclude-start DATE  Exclude templates overlapping this start date (YYYYMMDD)
  --dia-exclude-end DATE    Exclude templates overlapping this end date (YYYYMMDD)

Multi-night template building:
  --build-template          Build deep template after processing all nights
  --template-tract TRACT    Tract ID for template (required if --build-template)
  --template-band BAND      Band for template (required if --build-template)
  --template-patch PATCH    Specific patch (optional)

Examples:
  # Download from archive and process nights
  $0 --nights-file good_nights.txt

  # Process existing data (skip download)
  $0 --nights-file nights.txt --skip-download

  # Force re-download all files
  $0 --nights-file nights.txt --download-overwrite

  # Process specific nights with 16 parallel jobs
  $0 --nights "20240625,20240626,20240627" -j 16

  # Only run science (skip download and calibs)
  $0 --nights-file nights.txt --skip-download --skip-calibs

  # Process and build multi-night template
  $0 --nights-file nights.txt --build-template --template-tract 1099 --template-band r

  # Process with filtering
  $0 --nights-file nights.txt --object "2020wnt" --bad-file bad_exposures.txt

  # Process with difference imaging (auto-discover template)
  $0 --nights-file nights.txt --run-dia --dia-auto-template

  # DIA with specific template
  $0 --nights-file nights.txt --run-dia --dia-template "templates/deep/r"

  # DIA excluding supernova campaign dates (Feb 19-28, 2021)
  $0 --nights-file nights.txt --run-dia --dia-auto-template \\
    --dia-exclude-start 20210219 --dia-exclude-end 20210228

  # Dry run to see what would be executed
  $0 --nights-file nights.txt --dry-run

USAGE
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      exit 2
      ;;
  esac
done

########## VALIDATION ##########
if [[ -z "$NIGHTS_FILE" && -z "$NIGHTS_LIST" ]]; then
  echo "ERROR: Provide either --nights-file or --nights"
  exit 2
fi

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"
  exit 2
fi

if [[ "$BUILD_TEMPLATE" == "true" ]]; then
  if [[ -z "$TEMPLATE_TRACT" || -z "$TEMPLATE_BAND" ]]; then
    echo "ERROR: --build-template requires --template-tract and --template-band"
    exit 2
  fi
fi

if [[ "$SKIP_DOWNLOAD" == "true" && "$SKIP_CALIBS" == "true" && "$SKIP_SCIENCE" == "true" && "$RUN_DIA" == "false" ]]; then
  echo "ERROR: Cannot skip download, calibs, and science without DIA (nothing to do)"
  exit 2
fi

# DIA validation
if [[ "$RUN_DIA" == "true" ]]; then
  if [[ "$DIA_AUTO_TEMPLATE" == "false" && -z "$DIA_TEMPLATE" ]]; then
    echo "ERROR: --run-dia requires either --dia-auto-template or --dia-template"
    exit 2
  fi
  if [[ "$DIA_AUTO_TEMPLATE" == "true" && -n "$DIA_TEMPLATE" ]]; then
    echo "ERROR: Cannot use both --dia-auto-template and --dia-template"
    exit 2
  fi
  if [[ "$SKIP_SCIENCE" == "true" ]]; then
    echo "WARNING: --run-dia requires science processing (--skip-science will be ignored)"
    SKIP_SCIENCE=false
  fi
fi

########## BUILD NIGHTS ARRAY ##########
NIGHTS_ARRAY=()

if [[ -n "$NIGHTS_FILE" ]]; then
  if [[ ! -f "$NIGHTS_FILE" ]]; then
    echo "ERROR: Nights file not found: $NIGHTS_FILE"
    exit 2
  fi

  echo "[reading] Nights from file: $NIGHTS_FILE"
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Strip comments and whitespace
    night=$(echo "$line" | sed 's/#.*//' | tr -d ' \t\r\n')
    if [[ -n "$night" ]]; then
      # Validate format (YYYYMMDD)
      if [[ "$night" =~ ^[0-9]{8}$ ]]; then
        NIGHTS_ARRAY+=("$night")
      else
        echo "WARNING: Skipping invalid night format: '$night' (expected YYYYMMDD)"
      fi
    fi
  done < "$NIGHTS_FILE"
elif [[ -n "$NIGHTS_LIST" ]]; then
  echo "[reading] Nights from command line"
  # Parse comma-separated list
  IFS=',' read -ra NIGHTS_ARRAY <<< "$NIGHTS_LIST"
  # Trim whitespace and validate
  VALIDATED=()
  for night in "${NIGHTS_ARRAY[@]}"; do
    night=$(echo "$night" | tr -d ' \t\r\n')
    if [[ "$night" =~ ^[0-9]{8}$ ]]; then
      VALIDATED+=("$night")
    else
      echo "WARNING: Skipping invalid night format: '$night' (expected YYYYMMDD)"
    fi
  done
  NIGHTS_ARRAY=("${VALIDATED[@]}")
fi

if [[ ${#NIGHTS_ARRAY[@]} -eq 0 ]]; then
  echo "ERROR: No valid nights found"
  exit 2
fi

echo ""
echo "========================================"
echo "  BATCH PROCESSING: ${#NIGHTS_ARRAY[@]} NIGHTS"
echo "========================================"
echo "Nights: ${NIGHTS_ARRAY[*]}"
echo "Jobs: $JOBS"
echo "Skip download: $SKIP_DOWNLOAD"
echo "Skip calibs: $SKIP_CALIBS"
echo "Skip science: $SKIP_SCIENCE"
echo "Skip coadds: $SKIP_COADDS"
echo "Run DIA: $RUN_DIA"
if [[ "$RUN_DIA" == "true" ]]; then
  if [[ "$DIA_AUTO_TEMPLATE" == "true" ]]; then
    echo "  DIA template: auto-discover"
  else
    echo "  DIA template: $DIA_TEMPLATE"
  fi
fi
[[ "$DOWNLOAD_OVERWRITE" == "true" ]] && echo "Download mode: overwrite"
[[ -n "$OBJECT_FILTER" ]] && echo "Object filter: $OBJECT_FILTER"
[[ -n "$BAD_EXPOSURES_FILE" ]] && echo "Bad exposures file: $BAD_EXPOSURES_FILE"
[[ "$BUILD_TEMPLATE" == "true" ]] && echo "Build template: tract=$TEMPLATE_TRACT band=$TEMPLATE_BAND"
[[ "$DRY_RUN" == "true" ]] && echo "DRY RUN MODE (no commands executed)"
echo "========================================"
echo ""

########## SETUP ##########
mkdir -p "$LOG_DIR"

BATCH_TS="$(date -u +%Y%m%dT%H%M%SZ)"
BATCH_LOG="$LOG_DIR/batch_${BATCH_TS}.log"
SUMMARY_LOG="$LOG_DIR/batch_${BATCH_TS}_summary.txt"

# Write summary header
cat > "$SUMMARY_LOG" <<EOF
Batch Processing Summary
========================
Started: $(date)
Nights: ${#NIGHTS_ARRAY[@]}
Jobs: $JOBS

Configuration:
  Skip download: $SKIP_DOWNLOAD
  Download overwrite: $DOWNLOAD_OVERWRITE
  Skip calibs: $SKIP_CALIBS
  Skip science: $SKIP_SCIENCE
  Skip coadds: $SKIP_COADDS
  Run DIA: $RUN_DIA
  DIA template: ${DIA_TEMPLATE:-auto-discover}
  Object filter: ${OBJECT_FILTER:-none}
  Bad exposures file: ${BAD_EXPOSURES_FILE:-none}
  Build template: $BUILD_TEMPLATE
  Continue on error: $CONTINUE_ON_ERROR

Nights to process:
EOF

for night in "${NIGHTS_ARRAY[@]}"; do
  echo "  $night" >> "$SUMMARY_LOG"
done

echo "" >> "$SUMMARY_LOG"
echo "Processing Log:" >> "$SUMMARY_LOG"
echo "===============" >> "$SUMMARY_LOG"
echo "" >> "$SUMMARY_LOG"

# Track success/failures
SUCCESSFUL_NIGHTS=()
FAILED_NIGHTS=()

########## HELPER FUNCTIONS ##########
log_status() {
  local night="$1"
  local stage="$2"
  local status="$3"  # SUCCESS or FAILED
  local msg="[$(date +%H:%M:%S)] $night | $stage | $status"
  echo "$msg"
  echo "$msg" >> "$SUMMARY_LOG"
}

run_or_dry() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] $*"
    return 0
  else
    "$@"
  fi
}

########## PROCESS EACH NIGHT ##########
echo "Starting batch processing..."
echo "Logging to: $BATCH_LOG"
echo ""

for i in "${!NIGHTS_ARRAY[@]}"; do
  night="${NIGHTS_ARRAY[$i]}"
  night_num=$((i + 1))
  total_nights="${#NIGHTS_ARRAY[@]}"

  echo ""
  echo "========================================"
  echo "  NIGHT $night_num/$total_nights: $night"
  echo "========================================"
  echo ""

  NIGHT_SUCCESS=true

  # Stage 0: Download from archive
  if [[ "$SKIP_DOWNLOAD" == "false" ]]; then
    echo "[$night] Downloading from Lick archive (fetch_archive_night.py)..."
    log_status "$night" "download" "STARTED"

    DOWNLOAD_ARGS=(--night "$night")
    [[ "$DOWNLOAD_OVERWRITE" == "true" ]] && DOWNLOAD_ARGS+=(--overwrite)
    [[ -n "${LICK_ARCHIVE_DIR:-}" ]] && DOWNLOAD_ARGS+=(--client-path "$LICK_ARCHIVE_DIR")
    [[ -n "${RAW_PARENT_DIR:-}" ]] && DOWNLOAD_ARGS+=(--raw-root "$RAW_PARENT_DIR")

    # Use venv Python if available, otherwise system Python
    PYTHON_CMD="$OBS_NICKEL/scripts/python/pipeline_tools/fetch_archive_night.py"
    if [[ -n "${LICK_ARCHIVE_DIR:-}" && -f "${LICK_ARCHIVE_DIR}/.venv/bin/python" ]]; then
      PYTHON_CMD="${LICK_ARCHIVE_DIR}/.venv/bin/python $OBS_NICKEL/scripts/python/pipeline_tools/fetch_archive_night.py"
    fi

    if run_or_dry $PYTHON_CMD "${DOWNLOAD_ARGS[@]}" 2>&1 | tee -a "$BATCH_LOG"; then
      log_status "$night" "download" "SUCCESS"
    else
      log_status "$night" "download" "FAILED"
      NIGHT_SUCCESS=false
      if [[ "$CONTINUE_ON_ERROR" == "false" ]]; then
        echo "ERROR: Download failed for $night. Exiting."
        FAILED_NIGHTS+=("$night")
        break
      else
        echo "WARNING: Download failed for $night. Continuing to next night."
        FAILED_NIGHTS+=("$night")
        continue
      fi
    fi
  else
    log_status "$night" "download" "SKIPPED"
  fi

  # Stage 1: Calibrations
  if [[ "$SKIP_CALIBS" == "false" && "$NIGHT_SUCCESS" == "true" ]]; then
    echo "[$night] Running calibrations (10_calibs.sh)..."
    log_status "$night" "calibs" "STARTED"

    if run_or_dry "$OBS_NICKEL/scripts/pipeline/10_calibs.sh" --night "$night" 2>&1 | tee -a "$BATCH_LOG"; then
      log_status "$night" "calibs" "SUCCESS"
    else
      log_status "$night" "calibs" "FAILED"
      NIGHT_SUCCESS=false
      if [[ "$CONTINUE_ON_ERROR" == "false" ]]; then
        echo "ERROR: Calibration failed for $night. Exiting."
        FAILED_NIGHTS+=("$night")
        break
      else
        echo "WARNING: Calibration failed for $night. Continuing to next night."
        FAILED_NIGHTS+=("$night")
        continue
      fi
    fi
  else
    log_status "$night" "calibs" "SKIPPED"
  fi

  # Stage 2: Science processing
  if [[ "$SKIP_SCIENCE" == "false" && "$NIGHT_SUCCESS" == "true" ]]; then
    echo "[$night] Running science processing (20_science.sh)..."
    log_status "$night" "science" "STARTED"

    SCIENCE_ARGS=(--night "$night" -j "$JOBS")
    [[ "$SKIP_COADDS" == "true" ]] && SCIENCE_ARGS+=(--skip-coadds)
    [[ -n "$OBJECT_FILTER" ]] && SCIENCE_ARGS+=(--object "$OBJECT_FILTER")
    [[ -n "$BAD_EXPOSURES_FILE" ]] && SCIENCE_ARGS+=(--bad-file "$BAD_EXPOSURES_FILE")

    if run_or_dry "$OBS_NICKEL/scripts/pipeline/20_science.sh" "${SCIENCE_ARGS[@]}" 2>&1 | tee -a "$BATCH_LOG"; then
      log_status "$night" "science" "SUCCESS"
    else
      log_status "$night" "science" "FAILED"
      NIGHT_SUCCESS=false
      if [[ "$CONTINUE_ON_ERROR" == "false" ]]; then
        echo "ERROR: Science processing failed for $night. Exiting."
        FAILED_NIGHTS+=("$night")
        break
      else
        echo "WARNING: Science processing failed for $night. Continuing to next night."
        FAILED_NIGHTS+=("$night")
        continue
      fi
    fi
  else
    log_status "$night" "science" "SKIPPED"
  fi

  # Stage 3: Difference Imaging (DIA)
  if [[ "$RUN_DIA" == "true" && "$NIGHT_SUCCESS" == "true" ]]; then
    echo "[$night] Running difference imaging (40_diff_imaging.sh)..."
    log_status "$night" "DIA" "STARTED"

    DIA_ARGS=(--night "$night" -j "$JOBS")

    # Template selection
    if [[ "$DIA_AUTO_TEMPLATE" == "true" ]]; then
      DIA_ARGS+=(--auto-template)
    else
      DIA_ARGS+=(--template "$DIA_TEMPLATE")
    fi

    # Date exclusion for template selection
    if [[ -n "$DIA_EXCLUDE_START" && -n "$DIA_EXCLUDE_END" ]]; then
      DIA_ARGS+=(--exclude-start "$DIA_EXCLUDE_START" --exclude-end "$DIA_EXCLUDE_END")
    fi

    # Pass through filters
    [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
    [[ -n "$BAD_EXPOSURES_FILE" ]] && DIA_ARGS+=(--bad-file "$BAD_EXPOSURES_FILE")

    if run_or_dry "$OBS_NICKEL/scripts/pipeline/40_diff_imaging.sh" "${DIA_ARGS[@]}" 2>&1 | tee -a "$BATCH_LOG"; then
      log_status "$night" "DIA" "SUCCESS"
    else
      log_status "$night" "DIA" "FAILED"
      # DIA failure doesn't fail the whole night (science succeeded)
      if [[ "$CONTINUE_ON_ERROR" == "false" ]]; then
        echo "ERROR: DIA failed for $night. Exiting."
        FAILED_NIGHTS+=("$night")
        break
      else
        echo "WARNING: DIA failed for $night. Continuing to next night."
        # Don't add to FAILED_NIGHTS since science succeeded
      fi
    fi
  elif [[ "$RUN_DIA" == "true" ]]; then
    log_status "$night" "DIA" "SKIPPED (science failed)"
  fi

  # Track success
  if [[ "$NIGHT_SUCCESS" == "true" ]]; then
    SUCCESSFUL_NIGHTS+=("$night")
    echo "[$night] Completed successfully"
  fi

  # Progress indicator
  echo ""
  echo "Progress: $night_num/$total_nights nights processed"
  echo "  Successful: ${#SUCCESSFUL_NIGHTS[@]}"
  echo "  Failed: ${#FAILED_NIGHTS[@]}"
  echo ""
done

########## MULTI-NIGHT TEMPLATE ##########
if [[ "$BUILD_TEMPLATE" == "true" && ${#SUCCESSFUL_NIGHTS[@]} -gt 0 ]]; then
  echo ""
  echo "========================================"
  echo "  BUILDING MULTI-NIGHT TEMPLATE"
  echo "========================================"
  echo "Tract: $TEMPLATE_TRACT"
  echo "Band: $TEMPLATE_BAND"
  echo "Nights: ${#SUCCESSFUL_NIGHTS[@]}"
  echo ""

  log_status "multi-night" "template" "STARTED"

  # Create temporary nights file for successful nights
  TEMP_NIGHTS_FILE="$LOG_DIR/template_nights_${BATCH_TS}.txt"
  printf "%s\n" "${SUCCESSFUL_NIGHTS[@]}" > "$TEMP_NIGHTS_FILE"

  TEMPLATE_ARGS=(
    --tract "$TEMPLATE_TRACT"
    --band "$TEMPLATE_BAND"
    --nights-file "$TEMP_NIGHTS_FILE"
    -j "$JOBS"
  )
  [[ -n "$TEMPLATE_PATCH" ]] && TEMPLATE_ARGS+=(--patch "$TEMPLATE_PATCH")

  if run_or_dry "$OBS_NICKEL/scripts/pipeline/30_coadds.sh" "${TEMPLATE_ARGS[@]}" 2>&1 | tee -a "$BATCH_LOG"; then
    log_status "multi-night" "template" "SUCCESS"
  else
    log_status "multi-night" "template" "FAILED"
    echo "WARNING: Template building failed, but individual nights succeeded"
  fi

  # Clean up temp file
  rm -f "$TEMP_NIGHTS_FILE"
fi

########## FINAL SUMMARY ##########
echo "" | tee -a "$SUMMARY_LOG"
echo "========================================" | tee -a "$SUMMARY_LOG"
echo "  BATCH PROCESSING COMPLETE" | tee -a "$SUMMARY_LOG"
echo "========================================" | tee -a "$SUMMARY_LOG"
echo "Completed: $(date)" | tee -a "$SUMMARY_LOG"
echo "" | tee -a "$SUMMARY_LOG"
echo "Results:" | tee -a "$SUMMARY_LOG"
echo "  Total nights: ${#NIGHTS_ARRAY[@]}" | tee -a "$SUMMARY_LOG"
echo "  Successful: ${#SUCCESSFUL_NIGHTS[@]}" | tee -a "$SUMMARY_LOG"
echo "  Failed: ${#FAILED_NIGHTS[@]}" | tee -a "$SUMMARY_LOG"
echo "" | tee -a "$SUMMARY_LOG"

if [[ ${#SUCCESSFUL_NIGHTS[@]} -gt 0 ]]; then
  echo "Successful nights:" | tee -a "$SUMMARY_LOG"
  for night in "${SUCCESSFUL_NIGHTS[@]}"; do
    echo "  ✓ $night" | tee -a "$SUMMARY_LOG"
  done
  echo "" | tee -a "$SUMMARY_LOG"
fi

if [[ ${#FAILED_NIGHTS[@]} -gt 0 ]]; then
  echo "Failed nights:" | tee -a "$SUMMARY_LOG"
  for night in "${FAILED_NIGHTS[@]}"; do
    echo "  ✗ $night" | tee -a "$SUMMARY_LOG"
  done
  echo "" | tee -a "$SUMMARY_LOG"
fi

echo "Logs saved to:" | tee -a "$SUMMARY_LOG"
echo "  Batch log: $BATCH_LOG" | tee -a "$SUMMARY_LOG"
echo "  Summary: $SUMMARY_LOG" | tee -a "$SUMMARY_LOG"
echo "" | tee -a "$SUMMARY_LOG"

# Exit with error if any nights failed
if [[ ${#FAILED_NIGHTS[@]} -gt 0 ]]; then
  exit 1
else
  exit 0
fi
