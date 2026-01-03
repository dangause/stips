#!/usr/bin/env bash
# 30_coadds_recal.sh — Build coadds using recalibrated visit_summary
#
# This script builds coadds from recalibrated data (post-Stage 2).
# It uses the updated visit_summary that includes FGCM photometry and GBDES astrometry.

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.recal}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

# Source logging utilities
source "$(dirname "$0")/../utilities/logging.sh"

########## CLI ##########
NIGHTS_FILE=""
NIGHTS_LIST=""
TRACT=""
BAND=""
PATCH=""
INPUT_COLLECTIONS=""
OUTPUT_COLLECTION=""
JOBS="${JOBS:-8}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nights-file)     NIGHTS_FILE="${2:-}"; shift 2;;
    --nights)          NIGHTS_LIST="${2:-}"; shift 2;;
    --tract)           TRACT="${2:-}"; shift 2;;
    --band)            BAND="${2:-}"; shift 2;;
    --patch)           PATCH="${2:-}"; shift 2;;
    -i|--input)        INPUT_COLLECTIONS="${2:-}"; shift 2;;
    -o|--output)       OUTPUT_COLLECTION="${2:-}"; shift 2;;
    -j|--jobs)         JOBS="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --tract TRACT --band BAND [options]

Build deep multi-night coadd templates for difference imaging.

Required:
  --tract TRACT             Tract ID to process (e.g., 1099)
  --band BAND               Band to process (b, v, r, i)

Optional:
  --nights-file FILE        File with list of nights (YYYYMMDD, one per line)
  --nights NIGHTS           Comma-separated list of nights (e.g., "20240625,20240626")
  --patch PATCH             Specific patch ID (default: all patches in tract)
  -i, --input COLLECTIONS   Input collections (default: auto-discover from nights)
  -o, --output COLLECTION   Output collection (default: templates/deep/{tract}/{band})
  -j, --jobs N              Number of parallel jobs (default: ${JOBS})

Examples:
  # Build r-band template for tract 1099 from all available nights
  $0 --tract 1099 --band r

  # Build template from specific nights
  $0 --tract 1099 --band r --nights "20240625,20240626,20240627"

  # Build template from nights listed in file
  $0 --tract 1099 --band r --nights-file good_nights.txt

  # Build single patch
  $0 --tract 1099 --band r --patch 88
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Validate required args
[[ -n "$TRACT" ]] || { echo "ERROR: --tract required"; exit 2; }
[[ -n "$BAND" ]] || { echo "ERROR: --band required"; exit 2; }
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid -j/--jobs value: '$JOBS' (must be positive integer)"; exit 2;
fi

########## ENVIRONMENT ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
PIPE="$OBS_NICKEL/packages/obs_nickel/pipelines/experimental/DRP_recal.yaml"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

# Output collections
COADD_PARENT="Nickel/recal/coadds/tract${TRACT}/${BAND}/${RUN_TS}"
COADD_RUN="${COADD_PARENT}/run"

QG_DIR="$REPO/qgraphs/recal"; mkdir -p "$QG_DIR"
QG_COADD="$QG_DIR/coadds_t${TRACT}_${BAND}_${RUN_TS}.qg"

# Setup logging
setup_logging "coadds_recal" "" "$BAND" "$TRACT"

# Redirect all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Template Building"
log_info "Tract: $TRACT"
log_info "Band: $BAND"
log_info "RUN_TS: $RUN_TS"

########## LSST STACK ##########
# Save critical variables (LSST stack setup may clear them)
_SAVED_NIGHTS_FILE="$NIGHTS_FILE"
_SAVED_NIGHTS_LIST="$NIGHTS_LIST"
_SAVED_TRACT="$TRACT"
_SAVED_BAND="$BAND"
_SAVED_PATCH="$PATCH"
_SAVED_INPUT_COLLECTIONS="$INPUT_COLLECTIONS"
_SAVED_OUTPUT_COLLECTION="$OUTPUT_COLLECTION"
_SAVED_JOBS="$JOBS"

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Restore variables
NIGHTS_FILE="$_SAVED_NIGHTS_FILE"
NIGHTS_LIST="$_SAVED_NIGHTS_LIST"
TRACT="$_SAVED_TRACT"
BAND="$_SAVED_BAND"
PATCH="$_SAVED_PATCH"
INPUT_COLLECTIONS="$_SAVED_INPUT_COLLECTIONS"
OUTPUT_COLLECTION="$_SAVED_OUTPUT_COLLECTION"
JOBS="$_SAVED_JOBS"

# Validate files
[[ -s "$PIPE" ]] || { echo "ERROR: Pipeline not found: $PIPE"; exit 2; }

########## READ NIGHTS ##########
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

NIGHTS=($(read_nights "$NIGHTS_FILE"))
log_info "Processing ${#NIGHTS[@]} nights: ${NIGHTS[*]}"

########## FIND INPUT COLLECTIONS ##########
# We need both Stage 1 outputs (for preliminary_visit_image) and Stage 2 outputs (for visit_summary)
STAGE1_COLLECTIONS=()
for night in "${NIGHTS[@]}"; do
  LATEST_STAGE1=$(butler query-collections "$REPO" | awk '{print $1}' | \
    grep -E "^Nickel/recal/runs/${night}/stage1/" | tail -n1 || true)
  if [[ -z "$LATEST_STAGE1" ]]; then
    log_error "No Stage 1 collection found for night $night"
    exit 2
  fi
  STAGE1_COLLECTIONS+=("$LATEST_STAGE1")
done

# Find latest Stage 2 recalibration collection
STAGE2_COLLECTION=$(butler query-collections "$REPO" | awk '{print $1}' | \
  grep -E "^Nickel/recal/stage2/" | tail -n1 || true)
if [[ -z "$STAGE2_COLLECTION" ]]; then
  log_error "No Stage 2 recalibration collection found"
  log_error "Expected pattern: Nickel/recal/stage2/*"
  log_error "Run 21_recalibrate.sh first"
  exit 2
fi

# Build input collection list (Stage 1 collections + Stage 2 collection)
INPUT_COLLECTIONS="$(IFS=,; echo "${STAGE1_COLLECTIONS[*]}"),$STAGE2_COLLECTION"
log_info "Input collections: $INPUT_COLLECTIONS"

########## BUILD WHERE CLAUSE ##########
# Filter by band and nights
NIGHT_CSV="$(IFS=,; echo "${NIGHTS[*]}")"
WHERE_CLAUSE="instrument='Nickel' AND skymap='${SKYMAP_NAME}' AND tract=${TRACT} AND band='${BAND}' AND exposure.day_obs IN (${NIGHT_CSV})"

log_info "Where clause: $WHERE_CLAUSE"

########## BUILD QGRAPH ##########
log_section "Building Quantum Graph (Coadds)"
log_info "Quantum graph: $QG_COADD"

if ! pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#coadds-only" \
  -i "$INPUT_COLLECTIONS","$SKYMAPS_CHAIN" \
  -o "$COADD_PARENT" \
  --output-run "$COADD_RUN" \
  --save-qgraph "$QG_COADD" \
  -d "$WHERE_CLAUSE"; then
  log_error "Quantum graph generation failed"
  print_log_summary
  exit 2
fi

if [[ ! -s "$QG_COADD" ]]; then
  log_error "Quantum graph not created: $QG_COADD"
  print_log_summary
  exit 2
fi

########## RUN COADDS ##########
log_section "Running Coadd Pipeline"
COADD_LOG="$(get_task_log "coadds")"
log_info "Coadd log: $COADD_LOG"

if pipetask run \
    -b "$REPO" \
    -g "$QG_COADD" \
    --register-dataset-types \
    -j "$JOBS" \
    2>&1 | tee "$COADD_LOG"; then
  butler collection-chain "$REPO" "$COADD_PARENT" "$COADD_RUN" --mode redefine >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$COADD_PARENT" "$COADD_RUN"
  log_info "Coadds completed successfully"
else
  log_error "Coadds failed"
  log_error "Check log: $COADD_LOG"
  print_log_summary
  exit 2
fi

########## SUMMARY ##########
log_section "Coadds Complete"
echo "=== [coadds_recal] done ==="
echo "COADD_PARENT = $COADD_PARENT"
echo "COADD_RUN    = $COADD_RUN"
echo "BAND         = $BAND"
echo "TRACT        = $TRACT"

print_log_summary
