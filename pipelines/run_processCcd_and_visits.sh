REPO="/Users/dangause/Desktop/lick/lsst/data/nickel/062424"
RUN="Nickel/raw/all"
CALIB_CHAIN="Nickel/calib/current"
PIPE="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel/pipelines/ProcessCcd.yaml"
BAD="1032,1051,1052"
TS=$(date -u +%Y%m%dT%H%M%SZ)


pipetask run \
  -b "$REPO" \
  -i "$RUN","$CALIB_CHAIN","refcats" \
  -o Nickel/run/processCcd \
  -p "$PIPE#processCcd" \
  -C calibrateImage:configs/calibrateImage/tuned_configs/best_calib_t071.py \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  -j 1 --register-dataset-types \
  2>&1 | tee "logs/processCcd_${TS}.log"
  # -C calibrateImage:configs/apply_colorterms.py \
  # --debug \
  # -d "instrument='Nickel' AND exposure.observation_type='science' AND exposure IN (1042)" \
  # -d "instrument='Nickel' AND exposure.observation_type='science'" \


pipetask run \
  -b "$REPO" \
  -i "Nickel/run/processCcd","$CALIB_CHAIN","refcats" \
  -o Nickel/run/postproc/visits/$TS \
  -p ./pipelines/PostProcessing.yaml \
  --register-dataset-types \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  -j 4 \
  2>&1 | tee "logs/postproc_visits_${TS}.log"

