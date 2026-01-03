#!/usr/bin/env bash
# 21_recalibrate.sh — Stage 2 recalibration (FGCM + GBDES + PSF refit + visit_summary update)
#
# Runs the full Stage 2 recalibration pipeline:
#   - step2a: FGCM photometric calibration (global)
#   - step2b: GBDES astrometric fit (per-tract)
#   - step2c: GBDES healpix fit (optional, per-healpix)
#   - step2d: Refit PSFs, update visit_summary with new calibs
#   - step2f: Final tables and stellar motion fit

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
TRACT=""
OBJECT_FILTER=""
JOBS="${JOBS:-8}"
SKIP_STEP2A=false
SKIP_STEP2B=false
SKIP_STEP2C=false  # healpix step (optional)
SKIP_STEP2D=false
SKIP_STEP2F=false

usage() {
  cat <<USAGE
Usage: $0 --nights-file FILE --tract TRACT [options]

Runs Stage 2 recalibration steps (2a-2f) on Stage 1 outputs.

Required:
  --nights-file FILE       File with nights processed in Stage 1 (YYYYMMDD per line)
  --tract TRACT            Tract number for GBDES astrometric fit

Optional:
  --object NAME            OBJECT filter (must match Stage 1)
  -j, --jobs N             Parallel jobs (default: ${JOBS})

Skip Options:
  --skip-step2a            Skip FGCM (photometric calibration)
  --skip-step2b            Skip GBDES tract-level astrometric fit
  --skip-step2c            Skip GBDES healpix-level fit (optional step)
  --skip-step2d            Skip PSF refit and visit_summary update
  --skip-step2f            Skip final tables and stellar motion fit

Environment:
  ENV_FILE                 Environment file (default: .env.recal)
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nights-file)    NIGHTS_FILE="${2:-}"; shift 2;;
    --tract)          TRACT="${2:-}"; shift 2;;
    --object)         OBJECT_FILTER="${2:-}"; shift 2;;
    -j|--jobs)        JOBS="${2:-}"; shift 2;;
    --skip-step2a)    SKIP_STEP2A=true; shift;;
    --skip-step2b)    SKIP_STEP2B=true; shift;;
    --skip-step2c)    SKIP_STEP2C=true; shift;;
    --skip-step2d)    SKIP_STEP2D=true; shift;;
    --skip-step2f)    SKIP_STEP2F=true; shift;;
    -h|--help)        usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

########## VALIDATION ##########
[[ -n "$NIGHTS_FILE" ]] || { echo "ERROR: --nights-file required"; usage; }
[[ -f "$NIGHTS_FILE" ]] || { echo "ERROR: Nights file not found: $NIGHTS_FILE"; exit 2; }
[[ -n "$TRACT" ]] || { echo "ERROR: --tract required"; usage; }
[[ "$TRACT" =~ ^[0-9]+$ ]] || { echo "ERROR: --tract must be numeric"; exit 2; }

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "ERROR: Invalid --jobs value: '$JOBS'"; exit 2;
fi

########## ENVIRONMENT ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
PIPE="$OBS_NICKEL/packages/obs_nickel/pipelines/experimental/DRP_recal.yaml"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

# Output collections
RECAL_PARENT="Nickel/recal/stage2/${RUN_TS}"
RECAL_RUN="${RECAL_PARENT}/run"

QG_DIR="$REPO/qgraphs/recal"; mkdir -p "$QG_DIR"

# Setup logging
setup_logging "recalibrate"
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Stage 2 Recalibration"
log_info "Nights file: $NIGHTS_FILE"
log_info "Tract: $TRACT"
log_info "Jobs: $JOBS"
log_info "RUN_TS: $RUN_TS"
log_info "Pipeline: $PIPE"

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

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

########## FIND STAGE 1 COLLECTIONS ##########
# We need to find the Stage 1 output collections for these nights
# They should be named: Nickel/recal/runs/${NIGHT}/stage1/*
STAGE1_COLLECTIONS=()
for night in "${NIGHTS[@]}"; do
  LATEST_STAGE1=$(butler query-collections "$REPO" | awk '{print $1}' | \
    grep -E "^Nickel/recal/runs/${night}/stage1/" | tail -n1 || true)
  if [[ -z "$LATEST_STAGE1" ]]; then
    log_error "No Stage 1 collection found for night $night"
    log_error "Expected pattern: Nickel/recal/runs/${night}/stage1/*"
    exit 2
  fi
  STAGE1_COLLECTIONS+=("$LATEST_STAGE1")
  log_info "Stage 1 collection for $night: $LATEST_STAGE1"
done

# Build comma-separated input collection list
INPUT_COLLECTIONS="$(IFS=,; echo "${STAGE1_COLLECTIONS[*]}")"
log_info "Input collections: $INPUT_COLLECTIONS"

########## OBJECT FILTER ##########
OBJECT_EXPR=""
if [[ -n "$OBJECT_FILTER" ]]; then
  OBJECT_EXPR=" AND exposure.target_name='${OBJECT_FILTER}'"
  log_info "Object filter: ${OBJECT_FILTER}"
fi

########## STEP 2A: FGCM (Global Photometric Calibration) ##########
if [[ "$SKIP_STEP2A" == "false" ]]; then
  log_section "Step 2a: FGCM (Photometric Calibration)"
  QG_2A="$QG_DIR/step2a_${RUN_TS}.qg"

  log_info "Building quantum graph for step2a-recalibrate-global"
  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#step2a-recalibrate-global" \
    -i "$INPUT_COLLECTIONS","$SKYMAPS_CHAIN" \
    -o "$RECAL_PARENT" \
    --output-run "$RECAL_RUN" \
    --save-qgraph "$QG_2A" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}'${OBJECT_EXPR}"; then
    log_error "Quantum graph failed for step2a"
    exit 2
  fi

  [[ -s "$QG_2A" ]] || { log_error "QG not created: $QG_2A"; exit 2; }

  STEP2A_LOG="$(get_task_log "step2a_fgcm")"
  log_info "Running step2a (log: $STEP2A_LOG)"
  if pipetask run -b "$REPO" -g "$QG_2A" --register-dataset-types -j "$JOBS" \
      2>&1 | tee "$STEP2A_LOG"; then
    log_info "Step 2a completed successfully"
  else
    log_error "Step 2a failed (check: $STEP2A_LOG)"
    exit 2
  fi
else
  log_info "Skipping step2a (--skip-step2a)"
fi

########## STEP 2B: GBDES Tract-level Astrometry ##########
if [[ "$SKIP_STEP2B" == "false" ]]; then
  log_section "Step 2b: GBDES Tract-level Astrometric Fit"
  QG_2B="$QG_DIR/step2b_${RUN_TS}.qg"

  # Update input collections to include step2a outputs
  INPUTS_WITH_2A="$INPUT_COLLECTIONS,$RECAL_PARENT"

  log_info "Building quantum graph for step2b-recalibrate-tracts (tract=$TRACT)"
  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#step2b-recalibrate-tracts" \
    -i "$INPUTS_WITH_2A","$SKYMAPS_CHAIN" \
    -o "$RECAL_PARENT" \
    --output-run "$RECAL_RUN" \
    --save-qgraph "$QG_2B" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}' AND tract=${TRACT}${OBJECT_EXPR}"; then
    log_error "Quantum graph failed for step2b"
    exit 2
  fi

  [[ -s "$QG_2B" ]] || { log_error "QG not created: $QG_2B"; exit 2; }

  STEP2B_LOG="$(get_task_log "step2b_gbdes")"
  log_info "Running step2b (log: $STEP2B_LOG)"
  if pipetask run -b "$REPO" -g "$QG_2B" --register-dataset-types -j "$JOBS" \
      2>&1 | tee "$STEP2B_LOG"; then
    log_info "Step 2b completed successfully"
  else
    log_error "Step 2b failed (check: $STEP2B_LOG)"
    exit 2
  fi
else
  log_info "Skipping step2b (--skip-step2b)"
fi

########## STEP 2C: GBDES Healpix-level (Optional) ##########
if [[ "$SKIP_STEP2C" == "false" ]]; then
  log_section "Step 2c: GBDES Healpix-level Fit (Optional)"
  QG_2C="$QG_DIR/step2c_${RUN_TS}.qg"

  INPUTS_WITH_2B="$INPUT_COLLECTIONS,$RECAL_PARENT"

  log_info "Building quantum graph for step2c-recalibrate-healpix"
  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#step2c-recalibrate-healpix" \
    -i "$INPUTS_WITH_2B","$SKYMAPS_CHAIN" \
    -o "$RECAL_PARENT" \
    --output-run "$RECAL_RUN" \
    --save-qgraph "$QG_2C" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}'${OBJECT_EXPR}"; then
    log_warn "Quantum graph failed for step2c (healpix is optional, continuing)"
  else
    if [[ -s "$QG_2C" ]]; then
      STEP2C_LOG="$(get_task_log "step2c_healpix")"
      log_info "Running step2c (log: $STEP2C_LOG)"
      if pipetask run -b "$REPO" -g "$QG_2C" --register-dataset-types -j "$JOBS" \
          2>&1 | tee "$STEP2C_LOG"; then
        log_info "Step 2c completed successfully"
      else
        log_warn "Step 2c failed (healpix is optional, continuing)"
      fi
    fi
  fi
else
  log_info "Skipping step2c (--skip-step2c)"
fi

########## STEP 2D: Refit PSF + Update visit_summary ##########
if [[ "$SKIP_STEP2D" == "false" ]]; then
  log_section "Step 2d: Refit PSF and Update visit_summary"
  QG_2D="$QG_DIR/step2d_${RUN_TS}.qg"

  INPUTS_WITH_2ABC="$INPUT_COLLECTIONS,$RECAL_PARENT"

  log_info "Building quantum graph for step2d-recalibrate-visits"
  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#step2d-recalibrate-visits" \
    -i "$INPUTS_WITH_2ABC","$SKYMAPS_CHAIN" \
    -o "$RECAL_PARENT" \
    --output-run "$RECAL_RUN" \
    --save-qgraph "$QG_2D" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}' AND tract=${TRACT}${OBJECT_EXPR}"; then
    log_error "Quantum graph failed for step2d"
    exit 2
  fi

  [[ -s "$QG_2D" ]] || { log_error "QG not created: $QG_2D"; exit 2; }

  STEP2D_LOG="$(get_task_log "step2d_visits")"
  log_info "Running step2d (log: $STEP2D_LOG)"
  if pipetask run -b "$REPO" -g "$QG_2D" --register-dataset-types -j "$JOBS" \
      2>&1 | tee "$STEP2D_LOG"; then
    log_info "Step 2d completed successfully"
  else
    log_error "Step 2d failed (check: $STEP2D_LOG)"
    exit 2
  fi
else
  log_info "Skipping step2d (--skip-step2d)"
fi

########## STEP 2F: Final Tables ##########
if [[ "$SKIP_STEP2F" == "false" ]]; then
  log_section "Step 2f: Final Tables and Stellar Motion"
  QG_2F="$QG_DIR/step2f_${RUN_TS}.qg"

  INPUTS_WITH_ALL="$INPUT_COLLECTIONS,$RECAL_PARENT"

  log_info "Building quantum graph for step2f-recalibrate-global"
  if ! pipetask qgraph \
    -b "$REPO" \
    -p "$PIPE#step2f-recalibrate-global" \
    -i "$INPUTS_WITH_ALL","$SKYMAPS_CHAIN" \
    -o "$RECAL_PARENT" \
    --output-run "$RECAL_RUN" \
    --save-qgraph "$QG_2F" \
    -d "instrument='Nickel' AND skymap='${SKYMAP_NAME}'${OBJECT_EXPR}"; then
    log_error "Quantum graph failed for step2f"
    exit 2
  fi

  [[ -s "$QG_2F" ]] || { log_error "QG not created: $QG_2F"; exit 2; }

  STEP2F_LOG="$(get_task_log "step2f_tables")"
  log_info "Running step2f (log: $STEP2F_LOG)"
  if pipetask run -b "$REPO" -g "$QG_2F" --register-dataset-types -j "$JOBS" \
      2>&1 | tee "$STEP2F_LOG"; then
    log_info "Step 2f completed successfully"
  else
    log_error "Step 2f failed (check: $STEP2F_LOG)"
    exit 2
  fi
else
  log_info "Skipping step2f (--skip-step2f)"
fi

########## FINALIZE ##########
butler collection-chain "$REPO" "$RECAL_PARENT" "$RECAL_RUN" --mode redefine >/dev/null 2>&1 || \
butler collection-chain "$REPO" "$RECAL_PARENT" "$RECAL_RUN"

log_section "Stage 2 Recalibration Complete"
echo "=== [recalibrate] done ==="
echo "RECAL_PARENT = $RECAL_PARENT"
echo "RECAL_RUN    = $RECAL_RUN"
echo "TRACT        = $TRACT"

print_log_summary
