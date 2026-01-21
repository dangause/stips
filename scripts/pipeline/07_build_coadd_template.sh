#!/usr/bin/env bash
# 07_build_coadd_template.sh — Build deep coadd template from processed observations
#
# Usage:
#   ./scripts/07_build_coadd_template.sh --template-tag template_2020wnt \
#       --science-run "Nickel/templates/template_2020wnt/science/20251217T123456Z" \
#       --jobs 1

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

########## CLI ##########
TEMPLATE_TAG=""
SCIENCE_RUN=""
JOBS=1
TRACT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-tag) TEMPLATE_TAG="${2:-}"; shift 2;;
    --science-run) SCIENCE_RUN="${2:-}"; shift 2;;
    --tract) TRACT="${2:-}"; shift 2;;
    --jobs) JOBS="${2:-}"; shift 2;;
    -h|--help)
      cat <<USAGE
Usage: $0 --template-tag TAG --science-run RUN [options]

Build a deep coadded template from processed template observations.

Required:
  --template-tag TAG    Tag for template (e.g., template_2020wnt)
  --science-run RUN     Science processing output collection

Optional:
  --tract TRACT         Specific tract to process (default: all tracts)
  --jobs N              Number of parallel jobs (default: 1)
  -h, --help            Show this help

Example:
  $0 --template-tag template_2020wnt \\
     --science-run "Nickel/templates/template_2020wnt/science/20251217T123456Z" \\
     --tract 1825 \\
     --jobs 4

This will create a deep coadd template for difference imaging.
USAGE
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

[[ -n "$TEMPLATE_TAG" ]] || { echo "ERROR: Provide --template-tag"; exit 2; }
[[ -n "$SCIENCE_RUN" ]] || { echo "ERROR: Provide --science-run"; exit 2; }

########## SETUP ##########
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"

COADD_RUN="Nickel/templates/${TEMPLATE_TAG}/coadd/${RUN_TS}"
TEMPLATE_CHAIN="Nickel/templates/${TEMPLATE_TAG}"  # Stable alias

QG_DIR="$REPO/qgraphs"; mkdir -p "$QG_DIR"

echo "=== [build_coadd_template] Building template coadd: ${TEMPLATE_TAG} @ ${RUN_TS} ==="
echo "Science input: $SCIENCE_RUN"
echo "Coadd output:  $COADD_RUN"
echo ""

########## STACK ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
setup obs_nickel_data || true

########## Build Coadd ##########
TRACT_CLAUSE=""
if [[ -n "$TRACT" ]]; then
  TRACT_CLAUSE=" AND tract=${TRACT}"
  echo "[coadd] Processing tract $TRACT"
else
  echo "[coadd] Processing all tracts"
fi

echo "[coadds] makeWarp + assembleCoadd: $SCIENCE_RUN -> $COADD_RUN"
pipetask run \
  -b "$REPO" \
  -p "${OBS_NICKEL}/pipelines/DRP.yaml#coadds-only" \
  -i "$SCIENCE_RUN" \
  -o "$COADD_RUN" \
  -d "instrument='Nickel' AND skymap='nickel_skymap'${TRACT_CLAUSE}" \
  -j "$JOBS"

########## Create Template Chain ##########
echo "[chain] Creating stable template collection: $TEMPLATE_CHAIN"
butler collection-chain "$REPO" "$TEMPLATE_CHAIN" \
  "$COADD_RUN" \
  --mode redefine

echo ""
echo "=== [build_coadd_template] SUCCESS ==="
echo "Template coadd: $COADD_RUN"
echo "Stable chain:   $TEMPLATE_CHAIN"
echo ""
echo "You can now use this template for DIA:"
echo "  Template collection: $TEMPLATE_CHAIN"
echo ""
echo "Next step: Run DIA with science images"
echo "  ./scripts/40_diff_imaging.sh --night YYYYMMDD --template-collection $TEMPLATE_CHAIN"
