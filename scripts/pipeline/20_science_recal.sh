#!/usr/bin/env bash
# 20_science_recal.sh — Stage 1 science processing for DRP with recalibration
# This runs ONLY step1a-step1d (single-visit processing)
# Coadds are run separately after recalibration

# set -euo pipefail

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
NIGHT="${NIGHT:-}"
BAD_EXPOSURES=""; BAD_EXPOSURES_FILE=""
BAD_OBSIDS="";   BAD_OBSIDS_FILE=""
JOBS="${JOBS:-8}"
OBJECT_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)        NIGHT="${2:-}"; shift 2;;
    --bad)             BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)        BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    --bad-obs)         BAD_OBSIDS="${2:-}"; shift 2;;
    --bad-obs-file)    BAD_OBSIDS_FILE="${2:-}"; shift 2;;
    -j|--jobs)         JOBS="${2:-}"; shift 2;;
    --object)          OBJECT_FILTER="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --night YYYYMMDD [options]

Runs Stage 1 single-visit processing (step1a-step1d) for recalibration pipeline.
Does NOT run coadds - those are done after Stage 2 recalibration.

Options:
  --bad EXP_IDS             Comma- or space-separated exposure/visit IDs to exclude
  --bad-file FILE           File containing IDs to exclude (comments allowed)
  --bad-obs OBSNUMS         Comma- or space-separated OBSNUMs to exclude
  --bad-obs-file FILE       File containing OBSNUMs to exclude (comments allowed)
  -j, --jobs N              Number of parallel jobs (default: ${JOBS})
  --object NAME             Filter exposures by OBJECT header value

Environment:
  ENV_FILE                  Environment file (default: .env.recal)
USAGE
      exit 0;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done
[[ -n "$NIGHT" ]] || { echo "Provide --night YYYYMMDD"; exit 2; }

# Validate JOBS
if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "Invalid -j/--jobs value: '$JOBS'"; exit 2;
fi

########## ENVIRONMENT VARS ##########
INSTRUMENT="lsst.obs.nickel.Nickel"

# Pipeline & configs - USE RECAL PIPELINE
PIPE="$OBS_NICKEL/packages/obs_nickel/pipelines/experimental/DRP_recal.yaml"
# Tuned config that also loads colorterms
TUNED_CFG_FILE="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071_with_colorterms.py"
# Explicit colorterm loader (kept separate from standard pipeline files)
APPLY_CT_CFG="$OBS_NICKEL/configs/apply_colorterms.py"

# Skymap
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"
SKYMAP_NAME="${SKYMAP_NAME:-nickelRings-v1}"

########## TIMESTAMPS & COLLECTIONS ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/raw/${NIGHT}/${RUN_TS}"
CALIB_CHAIN="Nickel/calib/current"
REFCATS_CHAIN="refcats"

# Stage-1 outputs (recal-specific naming)
SCI_PARENT="Nickel/recal/runs/${NIGHT}/stage1/${RUN_TS}"
SCI_RUN="${SCI_PARENT}/run"

QG_DIR="$REPO/qgraphs/recal"; mkdir -p "$QG_DIR"
QG_SCI="$QG_DIR/stage1_${NIGHT}_${RUN_TS}.qg"
QG_SCI_DOT="$QG_DIR/stage1_${NIGHT}_${RUN_TS}.dot"
QG_SCI_MMD="$QG_DIR/stage1_${NIGHT}_${RUN_TS}.mmd"

# Setup logging (reuse existing science log layout for recal runs)
setup_logging "science" "$NIGHT"
exec > >(tee -a "$LOG_FILE") 2>&1

log_section "Science Stage 1 (Recal Pipeline)"
log_info "Night: $NIGHT"
log_info "Jobs: $JOBS"
log_info "RUN_TS: $RUN_TS"
log_info "Pipeline: $PIPE"

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

# Validate pipeline
[[ -s "$PIPE" ]] || { echo "ERROR: pipeline not found: $PIPE"; exit 2; }
[[ -s "$TUNED_CFG_FILE" ]] || { echo "ERROR: tuned config not found: $TUNED_CFG_FILE"; exit 2; }
[[ -s "$APPLY_CT_CFG" ]] || { echo "ERROR: colorterms config not found: $APPLY_CT_CFG"; exit 2; }

########## INPUT SANITY ##########
# Find latest raw run for the night
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$RAW_RUN"; then
  RAW_RUN="$(butler query-collections "$REPO" | awk '{print $1}' | grep -E "^Nickel/raw/${NIGHT}/" | tail -n1 || true)"
fi
[[ -n "$RAW_RUN" ]] || { echo "ERROR: No raw run found for night ${NIGHT}"; exit 2; }

# Confirm skyMap exists
if ! butler query-datasets "$REPO" skyMap --collections "$SKYMAPS_CHAIN" \
      --where "skymap='${SKYMAP_NAME}'" 2>/dev/null | grep -q skyMap; then
  echo "[ERROR] skyMap='${SKYMAP_NAME}' not found in '${SKYMAPS_CHAIN}'."
  exit 2
fi

echo "[inputs] RAW_RUN=$RAW_RUN  CALIB_CHAIN=$CALIB_CHAIN  REFCATS=$REFCATS_CHAIN  SKYMAPS=$SKYMAPS_CHAIN"

########## EXCLUSIONS ##########
BAD_LIST="$BAD_EXPOSURES"
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  BAD_LIST="$BAD_LIST"$'\n'"$(cat "$BAD_EXPOSURES_FILE")"
fi
if [[ -n "$BAD_OBSIDS" ]]; then
  BAD_LIST="$BAD_LIST"$'\n'"$BAD_OBSIDS"
fi
if [[ -n "$BAD_OBSIDS_FILE" && -f "$BAD_OBSIDS_FILE" ]]; then
  BAD_LIST="$BAD_LIST"$'\n'"$(cat "$BAD_OBSIDS_FILE")"
fi

BAD_EXP_CSV="$(
  printf "%s\n" "$BAD_LIST" | sed -E 's/#.*//; s/[^0-9]+/\n/g' \
  | awk 'NF' | sort -n -u | paste -sd, -
)"
BAD_EXPR=""
[[ -n "$BAD_EXP_CSV" ]] && BAD_EXPR=" AND NOT (exposure IN (${BAD_EXP_CSV}) OR visit IN (${BAD_EXP_CSV}))"

[[ -n "$BAD_EXP_CSV" ]] && echo "[exclude] exposure/visit: ${BAD_EXP_CSV}" || echo "[exclude] none"

########## OBJECT FILTER ##########
OBJECT_EXPR=""
if [[ -n "$OBJECT_FILTER" ]]; then
  OBJECT_EXPR=" AND exposure.target_name='${OBJECT_FILTER}'"
  echo "[object filter] ${OBJECT_FILTER}"
else
  echo "[object filter] none"
fi

########## BUILD QGRAPH (Stage 1 only) ##########
log_section "Building Quantum Graph (Stage 1)"
echo "[qgraph] Stage 1 -> $QG_SCI"

# Run step1a through step1d
if ! pipetask qgraph \
  -b "$REPO" \
  -p "$PIPE#step1a-single-visit-detectors,step1b-single-visit-visits,step1c-single-visit-tracts,step1d-single-visit-global" \
  -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN","$SKYMAPS_CHAIN" \
  -o "$SCI_PARENT" \
  --output-run "$SCI_RUN" \
  --save-qgraph "$QG_SCI" \
  --config-file "calibrateImage:${TUNED_CFG_FILE}" \
  --config-file "calibrateImage:${APPLY_CT_CFG}" \
  --qgraph-dot "$QG_SCI_DOT" \
  --qgraph-mermaid "$QG_SCI_MMD" \
  -d "instrument='Nickel' AND exposure.observation_type='science'${OBJECT_EXPR}${BAD_EXPR}"; then
  log_error "Quantum graph generation failed"
  print_log_summary
  exit 2
fi

if [[ ! -s "$QG_SCI" ]]; then
  log_error "Quantum graph not created: $QG_SCI"
  print_log_summary
  exit 2
fi

########## RUN STAGE 1 ##########
log_section "Running Stage 1 Pipeline"
STAGE1_LOG="$(get_task_log "stage1")"
log_info "Stage 1 log: $STAGE1_LOG"

if pipetask run \
    -b "$REPO" \
    -g "$QG_SCI" \
    --register-dataset-types \
    -j "$JOBS" \
    2>&1 | tee "$STAGE1_LOG"; then
  butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN" --mode redefine >/dev/null 2>&1 || \
  butler collection-chain "$REPO" "$SCI_PARENT" "$SCI_RUN"
  log_info "Stage 1 completed successfully"
else
  log_error "Stage 1 failed"
  log_error "Check log: $STAGE1_LOG"
  print_log_summary
  exit 2
fi

########## SUMMARY ##########
log_section "Stage 1 Complete"
echo "=== [science_recal stage1] done ==="
echo "RAW_RUN     = $RAW_RUN"
echo "CALIB_CHAIN = $CALIB_CHAIN"
echo "SCI_PARENT  = $SCI_PARENT"
echo "SCI_RUN     = $SCI_RUN"
echo "SKYMAP_NAME = $SKYMAP_NAME"

print_log_summary
