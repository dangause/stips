# LEGACY: This test script is superseded by `nickel science` (Python CLI).
# Paths below are site-specific and must be updated for your environment.
REPO="/Users/dangause/Developer/lick/lsst/data/nickel/062424"
RUN="Nickel/raw/all"
CALIB_CHAIN="Nickel/calib/current"
PIPE="/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/packages/obs_nickel/pipelines/ProcessCcd.yaml"
BAD="1032,1051,1052"
TS=$(date -u +%Y%m%dT%H%M%SZ)

export PYTHONPATH="/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/packages/obs_nickel:${PYTHONPATH}"

pipetask run \
  -b "$REPO" \
  -i "$RUN","$CALIB_CHAIN","refcats" \
  -o Nickel/run/processCcd/debug_psf \
  -p "$PIPE#processCcd" \
  -C calibrateImage:configs/apcorr_overrides.py \
  -C calibrateImage:configs/psf_detection_relaxed.py \
  -C calibrateImage:configs/psf_starselector_relaxed.py \
  -C calibrateImage:configs/astrometry_relaxed.py \
  # -C calibrateImage:configs/apply_colorterms.py \
  -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
  -j 1 --register-dataset-types \
  2>&1 | tee "logs/processCcd_only_${TS}.log"
  # --debug \
  # -d "instrument='Nickel' AND exposure.observation_type='science' AND exposure IN (1042)" \
  # -d "instrument='Nickel' AND exposure.observation_type='science'" \
