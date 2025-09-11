#!/usr/bin/env bash
# Nickel reduction pipeline v3.4 — creates refcats, cross-midnight calib validity
# set -euo pipefail

########## USER VARS ##########
NIGHT="20240624"                   # YYYYMMDD of the observing night you’re processing
BAD="1032,1047,1051,1052"               # exposures to exclude from science processing

# Paths
STACK_DIR="/Users/dangause/Desktop/lick/lsst/lsst_stack"
OBS_NICKEL="$STACK_DIR/stack/obs_nickel"
REFCAT_REPO="$STACK_DIR/stack/refcats"          # holds conversion scripts + converted tiles
RAWDIR="/Users/dangause/Desktop/lick/data/${NIGHT}/raw"

# Long-lived Butler repo (no date in path!)
REPO="/Users/dangause/Desktop/lick/lsst/data/nickel/repo"

# Optional tuned calibrateImage config
OVR="$OBS_NICKEL/configs/calibrateImage/tuned_configs/best_calib_t071.py"

########## DERIVED NAMES ##########
TS="$(date -u +%Y%m%dT%H%M%SZ)"
INSTRUMENT="lsst.obs.nickel.Nickel"

# ISO dates for certify (Astropy requires ISO). Extend validity through *next* UTC day.
NIGHT_ISO="${NIGHT:0:4}-${NIGHT:4:2}-${NIGHT:6:2}"
NEXT_ISO="$(date -u -j -v+1d -f '%Y%m%d' "$NIGHT" +'%Y-%m-%d')"    # end-exclusive 00:00:00 next day
NEXT2_ISO="$(date -u -j -v+2d -f '%Y%m%d' "$NIGHT" +'%Y-%m-%d')"

# Collections
RAW_COL="Nickel/raw/${NIGHT}"

CP_RUN_BIAS="Nickel/cp/${NIGHT}/bias/${TS}"      # RUN for bias build
CP_RUN_FLAT="Nickel/cp/${NIGHT}/flat/${TS}"      # RUN for flat build

CALIB_OUT="Nickel/calib/${NIGHT}"                # nightly CALIBRATION collection (certify target)

CURATED_CHAIN="Nickel/calib/curated"             # CHAINED
DEFECTS_ALIAS="Nickel/calib/defects/current"     # CHAINED pointer to latest defects RUN
CONTEXT_CHAIN="Nickel/context/${NIGHT}"          # CHAINED
REFCAT_CHAIN="refcats"                           # CHAINED (we’ll build with children)

# Refcat dataset-type names (must match conversion/ingest below)
GAIA_DT="gaia_dr3_20250728"
PS1_DT="panstarrs1_dr2_20250730"

# Outputs
PROCESS_CCD_RUN="Nickel/runs/${NIGHT}/processCcd/${TS}"   # RUN
POSTPROC_RUN="Nickel/runs/${NIGHT}/postproc/${TS}"        # RUN

# Pipelines
CP_PIPE_DIR="$OBS_NICKEL"
PIPE_PROC="$OBS_NICKEL/pipelines/ProcessCcd.yaml"
PIPE_POST="$OBS_NICKEL/pipelines/PostProcessing.yaml"

echo "=== Nickel pipeline starting @ $TS (night=$NIGHT) ==="

########## ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel
setup testdata_nickel || true

cd "$OBS_NICKEL"

########## REPO & INSTRUMENT ##########
if [ ! -f "$REPO/butler.yaml" ]; then
  butler create "$REPO"
fi
butler register-instrument "$REPO" "$INSTRUMENT" || true

########## INGEST RAWS / DEFINE VISITS ##########
butler ingest-raws "$REPO" "$RAWDIR" --transfer symlink --output-run "$RAW_COL"
butler define-visits "$REPO" Nickel || true

########## CURATED (idempotent) ##########
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CURATED_CHAIN"; then
  CURATED_RUN="Nickel/calib/curated/${TS}"
  echo "[curated] Writing curated calibs to $CURATED_RUN"
  butler write-curated-calibrations "$REPO" Nickel "$RAW_COL" --collection "$CURATED_RUN"
  butler collection-chain "$REPO" "$CURATED_CHAIN" "$CURATED_RUN" --mode redefine
else
  echo "[curated] Using existing curated chain: $CURATED_CHAIN"
fi

########## CP: BIAS ##########
pipetask run \
  -b "$REPO" \
  -i "$CURATED_CHAIN","$RAW_COL" \
  -o "$CP_RUN_BIAS" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml" \
  -d "instrument='Nickel' AND exposure.observation_type='bias'" \
  --register-dataset-types

########## CP: FLATS ##########
pipetask run \
  -b "$REPO" \
  -i "$CURATED_CHAIN","$RAW_COL","$CP_RUN_BIAS" \
  -o "$CP_RUN_FLAT" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml" \
  -c cpFlatIsr:doDark=False \
  -c cpFlatIsr:doOverscan=True \
  -d "instrument='Nickel' AND exposure.observation_type='flat'" \
  --register-dataset-types

########## DEFECTS (from flats) ##########
if butler query-datasets "$REPO" flat --collections "$CP_RUN_FLAT" | grep -q '^flat'; then
  DEF_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  DEFECTS_RUN="Nickel/calib/defects/${DEF_TS}"

  echo "[defects] Building from $CP_RUN_FLAT -> $DEFECTS_RUN"
  python "$OBS_NICKEL/scripts/defects/make_defects_from_flats.py" \
    --repo "$REPO" \
    --collection "$CP_RUN_FLAT" \
    --invert-manual-y \
    --manual-box 255 0 2 1024 \
    --manual-box 783 0 2 977 \
    --manual-box 1000 0 25 1024 \
    --manual-box 45 120 6 9 \
    --manual-box 980 200 12 8 \
    --register \
    --ingest \
    --defects-run "$DEFECTS_RUN" \
    --plot

  butler collection-chain "$REPO" "$DEFECTS_ALIAS" "$DEFECTS_RUN" --mode redefine
else
  echo "[defects] No flats found in $CP_RUN_FLAT; skipping defects."
fi

########## REFCATS — CONVERT (if needed), REGISTER, INGEST, CHAIN ##########
cd "$REFCAT_REPO"

# 1) GAIA DR3
if [ ! -f "data/gaia-refcat/filename_to_htm.ecsv" ]; then
  echo "[refcats][GAIA] Converting GAIA DR3 to tiles ..."
  convertReferenceCatalog \
    data/gaia-refcat/ \
    scripts/gaia_dr3_config.py \
    ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv \
    &> convert-gaia.log
fi

if ! butler query-dataset-types "$REPO" | awk '{print $1}' | grep -qx "$GAIA_DT"; then
  echo "[refcats][GAIA] Registering dataset type $GAIA_DT"
  butler register-dataset-type "$REPO" "$GAIA_DT" SimpleCatalog htm7
fi

if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "refcats/$GAIA_DT"; then
  echo "[refcats][GAIA] Ingesting tiles into 'refcats/$GAIA_DT'"
  butler ingest-files -t direct "$REPO" "$GAIA_DT" "refcats/$GAIA_DT" data/gaia-refcat/filename_to_htm.ecsv
fi

# 2) PS1 DR2
if [ ! -f "data/ps1-refcat/filename_to_htm.ecsv" ]; then
  echo "[refcats][PS1] Converting PS1 DR2 to tiles ..."
  convertReferenceCatalog \
    data/ps1-refcat/ \
    scripts/ps1_config.py \
    ./data/ps1_all_cones/merged_ps1_cones.csv \
    &> convert-ps1.log
fi

if ! butler query-dataset-types "$REPO" | awk '{print $1}' | grep -qx "$PS1_DT"; then
  echo "[refcats][PS1] Registering dataset type $PS1_DT"
  butler register-dataset-type "$REPO" "$PS1_DT" SimpleCatalog htm7
fi

if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "refcats/$PS1_DT"; then
  echo "[refcats][PS1] Ingesting tiles into 'refcats/$PS1_DT'"
  butler ingest-files -t direct "$REPO" "$PS1_DT" "refcats/$PS1_DT" data/ps1-refcat/filename_to_htm.ecsv
fi

# 3) Build/extend the refcats CHAINED collection with both children
echo "[refcats] Building CHAIN '$REFCAT_CHAIN' with children: refcats/$GAIA_DT, refcats/$PS1_DT"
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$REFCAT_CHAIN"; then
  butler collection-chain "$REPO" --mode redefine "$REFCAT_CHAIN" "refcats/$GAIA_DT" "refcats/$PS1_DT"
else
  butler collection-chain "$REPO" "$REFCAT_CHAIN" "refcats/$GAIA_DT" "refcats/$PS1_DT" --mode redefine
fi

cd "$OBS_NICKEL"

########## CERTIFY NIGHTLY CALIBS (end-exclusive at NEXT_ISO 00:00:00) ##########
butler certify-calibrations "$REPO" "$CP_RUN_BIAS" "$CALIB_OUT" bias \
  --begin-date "${NIGHT_ISO}T00:00:00" --end-date "${NEXT2_ISO}T00:00:00"

butler certify-calibrations "$REPO" "$CP_RUN_FLAT" "$CALIB_OUT" flat \
  --begin-date "${NIGHT_ISO}T00:00:00" --end-date "${NEXT2_ISO}T00:00:00"

########## CONTEXT CHAIN (INPUT ORDER MATTERS) ##########
# Nightly context = [nightly certified calibs] + [defects alias] + [curated] + [refcats]
butler collection-chain "$REPO" "$CONTEXT_CHAIN" \
  "$CALIB_OUT" "$DEFECTS_ALIAS" "$CURATED_CHAIN" "$REFCAT_CHAIN" \
  --mode redefine

########## SCIENCE PROCESSING ##########
butler query-collections "$REPO" | grep -E 'Nickel/calib/(curated|defects/current)|refcats' || true

pipetask run \
  -b "$REPO" \
  -i "$RAW_COL","$CONTEXT_CHAIN" \
  -o "$PROCESS_CCD_RUN" \
  -p "$PIPE_PROC#processCcd" \
  -C calibrateImage:"$OVR" \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  -j 8 --register-dataset-types \
  2>&1 | tee "logs/processCcd_${NIGHT}_${TS}.log"

pipetask run \
  -b "$REPO" \
  -i "$PROCESS_CCD_RUN","$CONTEXT_CHAIN" \
  -o "$POSTPROC_RUN" \
  -p "$PIPE_POST" \
  --register-dataset-types \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  -j 8 \
  2>&1 | tee "logs/postproc_${NIGHT}_${TS}.log"

########## SKYMAP (optional; runs *after* science succeeded) ##########
SKY_CFG="configs/makeSkyMap_discrete_auto.py"
python scripts/build_discrete_skymap_config.py \
  --repo "$REPO" \
  --collections "$PROCESS_CCD_RUN" \
  --dataset-type initial_pvi \
  --skymap-id nickel_discrete \
  --border-deg 0.05 \
  --out "$SKY_CFG"

butler register-skymap "$REPO" -C "$SKY_CFG" || true
butler query-datasets "$REPO" skyMap --where "skymap='nickel_discrete'" || true

echo "=== Done ==="
echo "Raw:         $RAW_COL"
echo "Curated:     $CURATED_CHAIN"
echo "Calib out:   $CALIB_OUT (valid ${NIGHT_ISO}T00 → ${NEXT_ISO}T00)"
echo "Defects:     ${DEFECTS_RUN:-<none>} (alias: $DEFECTS_ALIAS)"
echo "Refcats:     $REFCAT_CHAIN (children: refcats/$GAIA_DT, refcats/$PS1_DT)"
echo "Context:     $CONTEXT_CHAIN"
echo "Science run: $PROCESS_CCD_RUN"
echo "Postproc:    $POSTPROC_RUN"
