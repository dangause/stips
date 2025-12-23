#!/usr/bin/env bash
# 06_process_template.sh — Process template observations through calibs + science pipeline
#
# Usage:
#   ./scripts/06_process_template.sh --template-tag template_2020wnt --jobs 1

set -a
source .env
set +a

########## CLI ##########
TEMPLATE_TAG=""
JOBS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-tag) TEMPLATE_TAG="${2:-}"; shift 2;;
    --jobs) JOBS="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --template-tag TAG [--jobs N]

Process template observations through calibs and science pipelines.

Required:
  --template-tag TAG    Tag for template data (e.g., template_2020wnt)

Optional:
  --jobs N             Number of parallel jobs (default: 1)
  -h, --help           Show this help

Example:
  $0 --template-tag template_2020wnt --jobs 4

This will:
1. Ingest template raw data into Butler
2. Run calibration pipeline (bias, flat)
3. Run science processing (ISR, calibration, etc.)
USAGE
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

[[ -n "$TEMPLATE_TAG" ]] || { echo "ERROR: Provide --template-tag"; exit 2; }

########## SETUP ##########
TEMPLATE_DIR="${RAW_PARENT_DIR}/templates/${TEMPLATE_TAG}"
INSTRUMENT="lsst.obs.nickel.Nickel"

# Reference collections (same as regular science processing)
REFCATS_CHAIN="${REFCATS_CHAIN:-refcats}"
SKYMAPS_CHAIN="${SKYMAPS_CHAIN:-skymaps/nickelRings}"

if [[ ! -d "$TEMPLATE_DIR" ]]; then
  echo "ERROR: Template directory not found: $TEMPLATE_DIR" >&2
  echo "Run 05_build_template.sh first to download template data" >&2
  exit 2
fi

# Timestamps for collections
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

RAW_RUN="Nickel/templates/${TEMPLATE_TAG}/raw/${RUN_TS}"
CP_RUN_BIAS="Nickel/templates/${TEMPLATE_TAG}/cp/bias/${RUN_TS}"
CP_RUN_FLAT="Nickel/templates/${TEMPLATE_TAG}/cp/flat/${RUN_TS}"
CURATED_RUN="Nickel/templates/${TEMPLATE_TAG}/curated/${RUN_TS}"
SCIENCE_RUN="Nickel/templates/${TEMPLATE_TAG}/science/${RUN_TS}"

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"

echo "=== [process_template] Processing template: ${TEMPLATE_TAG} @ ${RUN_TS} ==="
echo "Template data: $TEMPLATE_DIR"
echo ""

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

########## INGEST RAWS ##########
butler register-instrument "$REPO" "$INSTRUMENT" >/dev/null 2>&1 || true

echo "[ingest] template raws -> $RAW_RUN"
butler ingest-raws "$REPO" "$TEMPLATE_DIR" --transfer copy --output-run "$RAW_RUN" 2>&1 | \
  grep -v "Datastore already contains" || true

butler define-visits "$REPO" Nickel

########## CURATED CALIBS ##########
echo "[curated] write -> $CURATED_RUN (scanning $RAW_RUN)"
butler write-curated-calibrations "$REPO" Nickel "$RAW_RUN" --collection "$CURATED_RUN"

########## cpBias ##########
echo "[cpBias] inputs=[$CURATED_RUN,$RAW_RUN] out=$CP_RUN_BIAS"
pipetask run \
  -b "$REPO" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml" \
  -i "$CURATED_RUN,$RAW_RUN" \
  -o "$CP_RUN_BIAS" \
  -d "instrument='Nickel' AND exposure.observation_type='bias'" \
  -j "$JOBS"

########## cpFlat ##########
echo "[cpFlat] inputs=[$CURATED_RUN,$CP_RUN_BIAS,$RAW_RUN] out=$CP_RUN_FLAT"
pipetask run \
  -b "$REPO" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml" \
  -i "$CURATED_RUN,$CP_RUN_BIAS,$RAW_RUN" \
  -o "$CP_RUN_FLAT" \
  -d "instrument='Nickel' AND exposure.observation_type='flat'" \
  -c cpFlatIsr:doDark=False \
  -c cpFlatIsr:doOverscan=True \
  -j "$JOBS"

########## Science Processing ##########
echo "[science] inputs=[$CP_RUN_FLAT,$CP_RUN_BIAS,$CURATED_RUN,$RAW_RUN,$REFCATS_CHAIN,$SKYMAPS_CHAIN] out=$SCIENCE_RUN"
pipetask run \
  -b "$REPO" \
  -p "${OBS_NICKEL}/pipelines/DRP.yaml#stage1-single-visit" \
  -i "$CP_RUN_FLAT,$CP_RUN_BIAS,$CURATED_RUN,$RAW_RUN,$REFCATS_CHAIN,$SKYMAPS_CHAIN" \
  -o "$SCIENCE_RUN" \
  -d "instrument='Nickel' AND exposure.observation_type='science'" \
  --config-file "calibrateImage:${OBS_NICKEL}/configs/apply_colorterms.py" \
  -j "$JOBS"

echo ""
echo "=== [process_template] SUCCESS ==="
echo "Template processed collections:"
echo "  Raw:     $RAW_RUN"
echo "  Bias:    $CP_RUN_BIAS"
echo "  Flat:    $CP_RUN_FLAT"
echo "  Science: $SCIENCE_RUN"
echo ""
echo "Next step: Build coadded template"
echo "  ./scripts/07_build_coadd_template.sh --template-tag $TEMPLATE_TAG --science-run $SCIENCE_RUN"
