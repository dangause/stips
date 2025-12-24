#!/usr/bin/env bash
#
# run_full_dia.sh - One-button Nickel DIA workflow (00 → 40)
#
# This script chains the numbered pipeline steps:
#   00_bootstrap_repo.sh
#   10_calibs.sh        (per night)
#   20_science.sh       (per night)
#   30_coadds.sh        (template build, optional if using existing template)
#   40_diff_imaging.sh  (per science night)
# It is intentionally thin: it just orchestrates the existing scripts with
# sensible defaults and minimal CLI knobs.
#
# Examples:
#   # Build template from template_nights.txt and run DIA on science_nights.txt
#   ./scripts/pipeline/run_full_dia.sh \
#     --template-nights template_nights.txt \
#     --science-nights science_nights.txt \
#     --band r \
#     --tract 1825 \
#     --object "2020wnt" \
#     --jobs 4
#
#   # Use an existing template collection and auto-template discovery
#   ./scripts/pipeline/run_full_dia.sh \
#     --science-nights science_nights.txt \
#     --band r \
#     --tract 1825 \
#     --auto-template \
#     --bad-sub-threshold 0.5
#
# Flags:
#   --science-nights FILE     Required; list of nights to process through 10/20/40
#   --template-nights FILE    Nights to use for template build (30); optional if
#                             you provide --template or --auto-template
#   --template COLLECTION     Use an existing template collection (skip 30)
#   --auto-template           Let 40_diff_imaging.sh auto-discover template (skip 30)
#   --band BAND               Required band for 30/40 (b/v/r/i)
#   --tract TRACT             Tract for 30/40
#   --object NAME             OBJECT header filter for 20/40
#   --jobs N                  Parallel jobs for numbered scripts (default: 4)
#   --bad-sub-threshold NUM   Override badSubtractionRatioThreshold in DIA (40)
#   --skip-bootstrap          Skip 00_bootstrap_repo.sh
#   --skip-template-build     Skip 30_coadds.sh even if template nights provided
#   --dry-run                 Print commands but do not run them
#
# Requirements:
#   - .env populated (REPO, STACK_DIR, OBS_NICKEL, etc.)
#   - Raw data already present (or download separately with 01_download_archive.sh)

set -euo pipefail

#######################################
# Helpers
#######################################

usage() {
  sed -n '1,120p' "$0" | sed 's/^#//'
  exit 1
}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

run_or_dry() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] $*"
  else
    log "Running: $*"
    "$@"
  fi
}

read_nights() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: Nights file not found: $file" >&2
    exit 2
  fi
  # shellcheck disable=SC2002
  cat "$file" | sed 's/#.*//' | sed '/^\s*$/d'
}

unique_nights() {
  tr ' ' '\n' | sed '/^\s*$/d' | sort -u
}

#######################################
# Defaults
#######################################

SCIENCE_NIGHTS_FILE=""
TEMPLATE_NIGHTS_FILE=""
TEMPLATE_COLLECTION=""
AUTO_TEMPLATE=false
BAND=""
TRACT=""
OBJECT_FILTER=""
JOBS="${JOBS:-4}"
BAD_SUB_THRESH=""
SKIP_BOOTSTRAP=false
SKIP_TEMPLATE_BUILD=false
DRY_RUN=false

#######################################
# Parse args
#######################################

while [[ $# -gt 0 ]]; do
  case "$1" in
    --science-nights)      SCIENCE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template-nights)     TEMPLATE_NIGHTS_FILE="${2:-}"; shift 2;;
    --template)            TEMPLATE_COLLECTION="${2:-}"; shift 2;;
    --auto-template)       AUTO_TEMPLATE=true; shift 1;;
    --band)                BAND="${2:-}"; shift 2;;
    --tract)               TRACT="${2:-}"; shift 2;;
    --object)              OBJECT_FILTER="${2:-}"; shift 2;;
    --jobs|-j)             JOBS="${2:-4}"; shift 2;;
    --bad-sub-threshold)   BAD_SUB_THRESH="${2:-}"; shift 2;;
    --skip-bootstrap)      SKIP_BOOTSTRAP=true; shift 1;;
    --skip-template-build) SKIP_TEMPLATE_BUILD=true; shift 1;;
    --dry-run)             DRY_RUN=true; shift 1;;
    -h|--help)             usage;;
    *) echo "Unknown arg: $1"; usage;;
  esac
done

#######################################
# Validate
#######################################

[[ -z "$SCIENCE_NIGHTS_FILE" ]] && { echo "ERROR: --science-nights is required"; exit 2; }
[[ ! -f "$SCIENCE_NIGHTS_FILE" ]] && { echo "ERROR: science nights file not found: $SCIENCE_NIGHTS_FILE"; exit 2; }
[[ -z "$BAND" ]] && { echo "ERROR: --band is required"; exit 2; }
[[ -z "$TRACT" ]] && log "NOTE: --tract not provided; 30/40 will rely on auto-tract (if supported)."

if [[ -n "$BAD_SUB_THRESH" ]]; then
  if ! [[ "$BAD_SUB_THRESH" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo "ERROR: --bad-sub-threshold must be numeric" >&2
    exit 2
  fi
fi

if [[ -z "$TEMPLATE_COLLECTION" && "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "true" && -z "$TEMPLATE_NIGHTS_FILE" ]]; then
  echo "ERROR: No template source specified (provide --template, --template-nights, or --auto-template)" >&2
  exit 2
fi

# Template build requires a tract
if [[ -z "$TEMPLATE_COLLECTION" && "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "false" && -z "$TRACT" ]]; then
  echo "ERROR: Template build selected but --tract not provided" >&2
  exit 2
fi

#######################################
# Environment
#######################################

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Run from repo root." >&2
  exit 2
fi

set -a
source .env
set +a

#######################################
# Nights lists
#######################################

SCIENCE_NIGHTS=($(read_nights "$SCIENCE_NIGHTS_FILE"))
if [[ ${#SCIENCE_NIGHTS[@]} -eq 0 ]]; then
  echo "ERROR: No nights found in $SCIENCE_NIGHTS_FILE" >&2
  exit 2
fi

TEMPLATE_NIGHTS=()
if [[ -n "$TEMPLATE_NIGHTS_FILE" ]]; then
  TEMPLATE_NIGHTS=($(read_nights "$TEMPLATE_NIGHTS_FILE"))
  if [[ ${#TEMPLATE_NIGHTS[@]} -eq 0 ]]; then
    echo "ERROR: No nights found in $TEMPLATE_NIGHTS_FILE" >&2
    exit 2
  fi
fi

# Unique nights for 10/20
ALL_NIGHTS=($(printf "%s\n" "${SCIENCE_NIGHTS[@]}" "${TEMPLATE_NIGHTS[@]}" | unique_nights))

#######################################
# Echo config
#######################################
log "======================================="
log "Nickel full DIA pipeline"
log "======================================="
log "Science nights:    ${SCIENCE_NIGHTS[*]}"
[[ ${#TEMPLATE_NIGHTS[@]} -gt 0 ]] && log "Template nights:    ${TEMPLATE_NIGHTS[*]}" || log "Template nights:    (none provided)"
log "Band:              $BAND"
[[ -n "$TRACT" ]] && log "Tract:             $TRACT"
[[ -n "$OBJECT_FILTER" ]] && log "Object filter:     $OBJECT_FILTER"
log "Jobs:              $JOBS"
if [[ -n "$BAD_SUB_THRESH" ]]; then
  log "badSubThreshold:   $BAD_SUB_THRESH"
fi
if [[ -n "$TEMPLATE_COLLECTION" ]]; then
  log "Template source:   $TEMPLATE_COLLECTION (existing)"
elif [[ "$AUTO_TEMPLATE" == "true" ]]; then
  log "Template source:   auto-template discovery"
else
  log "Template source:   build via 30_coadds"
fi
[[ "$SKIP_BOOTSTRAP" == "true" ]] && log "Skip bootstrap:    yes"
[[ "$SKIP_TEMPLATE_BUILD" == "true" ]] && log "Skip template build: yes"
[[ "$DRY_RUN" == "true" ]] && log "*** DRY RUN ***"
log "======================================="

#######################################
# Stage 0: Bootstrap
#######################################
if [[ "$SKIP_BOOTSTRAP" == "false" ]]; then
  run_or_dry ./scripts/pipeline/00_bootstrap_repo.sh
else
  log "Skipping bootstrap (--skip-bootstrap)"
fi

#######################################
# Stage 1: Calibs (10)
#######################################
for night in "${ALL_NIGHTS[@]}"; do
  run_or_dry ./scripts/pipeline/10_calibs.sh --night "$night"
done

#######################################
# Stage 2: Science (20)
#######################################
for night in "${ALL_NIGHTS[@]}"; do
  SCI_ARGS=(--night "$night" -j "$JOBS" --skip-coadds)
  [[ -n "$OBJECT_FILTER" ]] && SCI_ARGS+=(--object "$OBJECT_FILTER")
  run_or_dry ./scripts/pipeline/20_science.sh "${SCI_ARGS[@]}"
done

#######################################
# Stage 3: Template build (30)
#######################################
if [[ -z "$TEMPLATE_COLLECTION" && "$AUTO_TEMPLATE" == "false" && "$SKIP_TEMPLATE_BUILD" == "false" ]]; then
  if [[ ${#TEMPLATE_NIGHTS[@]} -eq 0 ]]; then
    echo "ERROR: Template build requested but no --template-nights provided." >&2
    exit 2
  fi

  TMP_NIGHTS_FILE="$(mktemp)"
  printf "%s\n" "${TEMPLATE_NIGHTS[@]}" > "$TMP_NIGHTS_FILE"

  COADD_ARGS=(--nights-file "$TMP_NIGHTS_FILE" --band "$BAND" -j "$JOBS")
  [[ -n "$TRACT" ]] && COADD_ARGS+=(--tract "$TRACT")

  run_or_dry ./scripts/pipeline/30_coadds.sh "${COADD_ARGS[@]}"

  # Pick latest template collection for this tract/band
  TEMPLATE_COLLECTION="$(butler query-collections "$REPO" 2>/dev/null | awk '{print $1}' \
    | grep "templates/deep/tract${TRACT}/${BAND}" | tail -n1 || true)"

  if [[ -z "$TEMPLATE_COLLECTION" ]]; then
    echo "ERROR: Could not find template collection after 30_coadds" >&2
    exit 2
  fi
  log "Using built template: $TEMPLATE_COLLECTION"
fi

#######################################
# Stage 4: DIA (40)
#######################################
for night in "${SCIENCE_NIGHTS[@]}"; do
  DIA_ARGS=(--night "$night" -j "$JOBS" --band "$BAND")
  [[ -n "$TRACT" ]] && DIA_ARGS+=(--tract "$TRACT")
  [[ -n "$OBJECT_FILTER" ]] && DIA_ARGS+=(--object "$OBJECT_FILTER")
  if [[ -n "$TEMPLATE_COLLECTION" ]]; then
    DIA_ARGS+=(--template "$TEMPLATE_COLLECTION")
  elif [[ "$AUTO_TEMPLATE" == "true" ]]; then
    DIA_ARGS+=(--auto-template)
  else
    # Safety net: if no template source resolved, fall back to auto
    DIA_ARGS+=(--auto-template)
  fi
  if [[ -n "$BAD_SUB_THRESH" ]]; then
    DIA_ARGS+=(--bad-sub-threshold "$BAD_SUB_THRESH")
  fi
  run_or_dry ./scripts/pipeline/40_diff_imaging.sh "${DIA_ARGS[@]}"
done

log "======================================="
log "Full DIA workflow complete"
log "Science nights processed: ${SCIENCE_NIGHTS[*]}"
log "Template collection: ${TEMPLATE_COLLECTION:-auto-discovered}"
log "======================================="
