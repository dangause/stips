STACK_DIR="/Users/dangause/Developer/lick/lsst/lsst_stack"
REPO="/Users/dangause/Developer/lick/lsst/data/nickel/062424"
OBS="${HOME}/Developer/lick/lsst/lsst_stack/stack/obs_nickel"
CALIB="Nickel/calib/current"
REFCATS="refcats"
RAW_IN="Nickel/raw/all"
BAD="1032,1048,1051,1052"

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="Nickel/run/processCcd/${TS}"
POST="${OUT}/post"


########## BASIC CONFIG ##########
echo "=== Nickel pipeline starting @ $TS ==="

cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib; setup obs_nickel; setup testdata_nickel

cd "$OBS"


# 1) Full ProcessCcd with tuned calibrateImage overrides
pipetask run \
  -b "${REPO}" \
  -i "${RAW_IN},${CALIB},${REFCATS}" \
  -o "${OUT}" \
  -p "${OBS}/pipelines/ProcessCcd.yaml" \
  -C calibrateImage:configs/calibrateImage/tuned_configs/best_calib_t071.py \
  --register-dataset-types \
  -j 1 \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  2>&1 | tee "logs/processCcd_${TS}.log"

# 2) PostProcessing
pipetask run \
  -b "${REPO}" \
  -i "${OUT},${CALIB},${REFCATS}" \
  -o "${POST}" \
  -p "${OBS}/pipelines/PostProcessing.yaml" \
  --register-dataset-types \
  -j 1 \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  2>&1 | tee "logs/postproc_visits_${TS}.log"
