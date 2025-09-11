#!/usr/bin/env bash
# Nickel reduction pipeline — persistent repo, nightly certification

########## USER PATHS ##########
NIGHT="20240624"                               # night tag for this dataset
# NIGHT="20240524"
RAWDIR="/Users/dangause/Desktop/lick/data/${NIGHT}/raw"                       # raw data directory
REPO="/Users/dangause/Desktop/lick/lsst/data/nickel/repo"                    # persistent Butler repo
OBS_NICKEL="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel"   # obs_nickel directory
REFCAT_REPO="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/refcats"     # refcat working repo
STACK_DIR="/Users/dangause/Desktop/lick/lsst/lsst_stack"                      # lsst_stack (has loadLSST.zsh)

########## BASIC CONFIG ##########
INSTRUMENT="lsst.obs.nickel.Nickel"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RAW_RUN="Nickel/raw/${NIGHT}/${TS}"
CP_RUN_BIAS="Nickel/cp/${NIGHT}/bias/${TS}"
CP_RUN_FLAT="Nickel/cp/${NIGHT}/flat/${TS}"
CURATED_RUN="Nickel/calib/curated/${TS}"
DEFECTS_RUN="Nickel/calib/defects/${TS}"
CALIB_OUT="Nickel/calib/${NIGHT}"              # nightly CALIBRATION collection
CALIB_CHAIN="Nickel/calib/current"             # unified chain used by science
BAD=""                                          # exposures to exclude (none for now)
# BAD="1032,1047,1051,1052"                           # science exposures to exclude

echo "=== Nickel pipeline starting @ $TS (night=$NIGHT) ==="

########## LSST ENV ##########
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib; setup obs_nickel; setup testdata_nickel

########## REPO SETUP ##########
if [ ! -f "$REPO/butler.yaml" ]; then
  butler create "$REPO"
fi
butler register-instrument "$REPO" "$INSTRUMENT" || true

########## INGEST RAWS (unique run each time to avoid duplicates) ##########
echo "[ingest] Ingesting raws to $RAW_RUN (transfer=copy)"
butler ingest-raws "$REPO" "$RAWDIR" --transfer copy --output-run "$RAW_RUN"
butler define-visits "$REPO" Nickel
echo "[$RAW_RUN]"

########## CURATED CALIBS ##########
echo "[curated] Writing curated calibrations -> $CURATED_RUN"
butler write-curated-calibrations "$REPO" Nickel "$RAW_RUN" --collection "$CURATED_RUN"
# Maintain a simple curated chain that always points to the latest curated run
butler collection-chain "$REPO" Nickel/calib/curated "$CURATED_RUN" --mode redefine

########## CP: BIAS ##########
echo "[cpBias] $CP_RUN_BIAS"
pipetask run \
  -b "$REPO" \
  -i "$CURATED_RUN","$RAW_RUN" \
  -o "$CP_RUN_BIAS" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml" \
  -d "instrument='Nickel' AND exposure.observation_type='bias'" \
  --register-dataset-types

########## CP: FLATS ##########
echo "[cpFlat] $CP_RUN_FLAT"
pipetask run \
  -b "$REPO" \
  -i "$CURATED_RUN","$RAW_RUN","$CP_RUN_BIAS" \
  -o "$CP_RUN_FLAT" \
  -p "$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml" \
  -c cpFlatIsr:doDark=False \
  -c cpFlatIsr:doOverscan=True \
  -d "instrument='Nickel' AND exposure.observation_type='flat'" \
  --register-dataset-types

########## DEFECTS (from flats) ##########
echo "[defects] Building from $CP_RUN_FLAT -> $DEFECTS_RUN"
python "$OBS_NICKEL"/scripts/defects/make_defects_from_flats.py \
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
echo "DEFECTS_RUN = $DEFECTS_RUN"

# Point the defects/current chain at the latest defects run
butler collection-chain "$REPO" Nickel/calib/defects/current "$DEFECTS_RUN" --mode redefine
butler query-collections "$REPO" | grep -E 'Nickel/calib/defects/current|Nickel/calib/curated' || true

########## REF CATS (ingest & chain) ##########
cd "$REFCAT_REPO"
# GAIA DR3
if [ ! -d "refcats/gaia_dr3_20250728" ] || [ -z "$(ls -A refcats/gaia_dr3_20250728 2>/dev/null || true)" ]; then
  echo "[refcats][GAIA] Converting…"
  convertReferenceCatalog data/gaia-refcat/ scripts/gaia_dr3_config.py ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv &> convert-gaia.log
fi
echo "[refcats][GAIA] Registering dataset type gaia_dr3_20250728"
butler register-dataset-type "$REPO" gaia_dr3_20250728 SimpleCatalog htm7 || true
echo "[refcats][GAIA] Ingesting tiles into 'refcats/gaia_dr3_20250728'"
butler ingest-files -t direct "$REPO" gaia_dr3_20250728 refcats/gaia_dr3_20250728 data/gaia-refcat/filename_to_htm.ecsv

# PS1 DR2
if [ ! -d "refcats/panstarrs1_dr2_20250730" ] || [ -z "$(ls -A refcats/panstarrs1_dr2_20250730 2>/dev/null || true)" ]; then
  echo "[refcats][PS1] Converting…"
  convertReferenceCatalog data/ps1-refcat/ scripts/ps1_config.py ./data/ps1_all_cones/merged_ps1_cones.csv &> convert-ps1.log
fi
echo "[refcats][PS1] Registering dataset type panstarrs1_dr2_20250730"
butler register-dataset-type "$REPO" panstarrs1_dr2_20250730 SimpleCatalog htm7 || true
echo "[refcats][PS1] Ingesting tiles into 'refcats/panstarrs1_dr2_20250730'"
butler ingest-files -t direct "$REPO" panstarrs1_dr2_20250730 refcats/panstarrs1_dr2_20250730 data/ps1-refcat/filename_to_htm.ecsv

# Build/refresh the CHAIN collection "refcats"
echo "[refcats] Building CHAIN 'refcats' with children: refcats/gaia_dr3_20250728, refcats/panstarrs1_dr2_20250730"
butler collection-chain "$REPO" refcats \
  refcats/gaia_dr3_20250728 refcats/panstarrs1_dr2_20250730 \
  --mode redefine
butler query-collections "$REPO" | grep -E '^refcats$|^  refcats/' || true

# --- NIGHTLY CERTIFICATION WINDOW (robust) ---
export NIGHT   # ensure available to subprocesses

BEGIN_ISO="$(
python - "$NIGHT" <<'PY'
from datetime import datetime, timezone, timedelta
import sys
night = sys.argv[1]
dt = datetime.strptime(night, "%Y%m%d").replace(tzinfo=timezone.utc)
print(dt.strftime("%Y-%m-%dT%H:%M:%S"))
PY
)"

END_ISO="$(
python - "$NIGHT" <<'PY'
from datetime import datetime, timezone, timedelta
import sys
night = sys.argv[1]
dt = datetime.strptime(night, "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(days=2)
print(dt.strftime("%Y-%m-%dT%H:%M:%S"))
PY
)"

echo "[window] Certify range: $BEGIN_ISO → $END_ISO (UTC)"


########## CERTIFY CP CALIBS INTO NIGHTLY CALIBRATION COLLECTION ##########
# Check if nightly CALIB collection exists before querying datasets inside it.
if butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$CALIB_OUT"; then
  echo "[check] Nightly calib collection exists: $CALIB_OUT"
  HAS_BIAS=$(butler query-datasets "$REPO" bias --collections "$CALIB_OUT" \
              --where "instrument='Nickel'" | awk 'NR>1{print}' | wc -l | tr -d ' ')
  HAS_FLAT=$(butler query-datasets "$REPO" flat --collections "$CALIB_OUT" \
              --where "instrument='Nickel'" | awk 'NR>1{print}' | wc -l | tr -d ' ')
else
  echo "[check] Nightly calib collection not found yet: $CALIB_OUT (fresh repo)."
  HAS_BIAS=0
  HAS_FLAT=0
fi

if [ "$HAS_BIAS" -eq 0 ]; then
  echo "[certify] Certifying BIAS into $CALIB_OUT for $BEGIN_ISO → $END_ISO"
  butler certify-calibrations "$REPO" "$CP_RUN_BIAS" "$CALIB_OUT" bias \
    --begin-date "$BEGIN_ISO" --end-date "$END_ISO"
else
  echo "[certify] Bias already present in $CALIB_OUT — skipping."
fi

if [ "$HAS_FLAT" -eq 0 ]; then
  echo "[certify] Certifying FLAT into $CALIB_OUT for $BEGIN_ISO → $END_ISO"
  butler certify-calibrations "$REPO" "$CP_RUN_FLAT" "$CALIB_OUT" flat \
    --begin-date "$BEGIN_ISO" --end-date "$END_ISO"
else
  echo "[certify] Flats already present in $CALIB_OUT — skipping."
fi

########## BUILD UNIFIED CALIB CHAIN ##########
echo "[calib-chain] ${CALIB_CHAIN} = [$CALIB_OUT, Nickel/calib/defects/current, Nickel/calib/curated]"
butler collection-chain "$REPO" "$CALIB_CHAIN" \
  "$CALIB_OUT" Nickel/calib/defects/current Nickel/calib/curated \
  --mode redefine

########## SCIENCE PROCESSING ##########
cd "$OBS_NICKEL"
PIPE="$OBS_NICKEL/pipelines/ProcessCcd.yaml"
PROCESS_CCD_RUN="Nickel/runs/${NIGHT}/processCcd/${TS}"

# sanity
butler query-collections "$REPO" | grep -E 'Nickel/calib/(current|defects/current)|^refcats$' || true

# Exclude known-bad exposures (comma-separated list of exposure IDs)
if [[ -n "$BAD" ]]; then
  BAD_EXPR="AND NOT (exposure IN (${BAD}))"
else
  BAD_EXPR=""
fi


echo "[science] ProcessCcd -> $PROCESS_CCD_RUN"
pipetask run \
  -b "$REPO" \
  -i "$RAW_RUN","$CALIB_CHAIN","refcats" \
  -o "$PROCESS_CCD_RUN" \
  -p "$PIPE#processCcd" \
  -C calibrateImage:configs/calibrateImage/tuned_configs/best_calib_t071.py \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}" \
  -j 8 --register-dataset-types \
  2>&1 | tee "logs/processCcd_${TS}.log"

echo "[postproc] Visits"
pipetask run \
  -b "$REPO" \
  -i "$PROCESS_CCD_RUN","$CALIB_CHAIN","refcats" \
  -o "Nickel/run/postproc/visits/${TS}" \
  -p "$OBS_NICKEL/pipelines/PostProcessing.yaml" \
  --register-dataset-types \
  -d "instrument='Nickel' AND exposure.observation_type='science' ${BAD_EXPR}" \
  -j 8 \
  2>&1 | tee "logs/postproc_visits_${TS}.log"

########## SKYMAP (discrete from initial_pvi) ##########
cd "$OBS_NICKEL"
SKY_CFG="configs/makeSkyMap_discrete_auto.py"

# Only build/register a skymap if we actually produced initial_pvi
if butler query-datasets "$REPO" initial_pvi --collections "$PROCESS_CCD_RUN" | awk 'NR>1{print}' | grep -q .; then
  echo "[skymap] Building discrete skymap config from $PROCESS_CCD_RUN (initial_pvi)"
  python scripts/build_discrete_skymap_config.py \
    --repo "$REPO" \
    --collections "$PROCESS_CCD_RUN" \
    --dataset-type initial_pvi \
    --skymap-id nickel_discrete \
    --border-deg 0.05 \
    --out "$SKY_CFG"

  echo "[skymap] Registering"
  butler register-skymap "$REPO" -C "$SKY_CFG"
  butler query-datasets "$REPO" skyMap --where "skymap='nickel_discrete'" || true
else
  echo "[skymap] No 'initial_pvi' found in [$PROCESS_CCD_RUN]; skipping skymap."
fi

########## SUMMARY ##########
echo "=== Done ==="
echo "Raw run:     $RAW_RUN"
echo "Curated run: $CURATED_RUN"
echo "CP Bias:     $CP_RUN_BIAS"
echo "CP Flat:     $CP_RUN_FLAT"
echo "Defects run: $DEFECTS_RUN"
echo "Night calib: $CALIB_OUT"
echo "Calib chain: $CALIB_CHAIN"
echo "Science run: $PROCESS_CCD_RUN"
