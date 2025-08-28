#!/usr/bin/env bash

# Exit on first error
set -e

# Bad exposures - exclude from science processing
BAD="1032,1033,1034,1043,1046,1047,1048,1049,1050,1051,1052,1056,1058,1059,1060"

########## ABSOLUTE PATHS (edit if needed) ##########
LSST_STACK="/Users/dangause/Desktop/lick/lsst/lsst_stack"
REPO="/Users/dangause/Desktop/lick/lsst/data/nickel/062424"
RAWDIR="/Users/dangause/Desktop/lick/data/062424/raw"
OBS_NICKEL="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel"
REFCAT_REPO="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/refcats"
LOGS_DIR="$OBS_NICKEL/logs"

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

# Basic config variables
INSTRUMENT="lsst.obs.nickel.Nickel"
RUN="Nickel/raw/all"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

# Initialize flags
SKIP_CALIBS=false
SKIP_REFCATS=false

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --skip-calibs) SKIP_CALIBS=true ;;
        --skip-refcats) SKIP_REFCATS=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "=== Nickel pipeline starting @ $TS ===" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"
echo "Skipping calibrations: $SKIP_CALIBS" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"
echo "Skipping refcats: $SKIP_REFCATS" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"
echo "-------------------------------------" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"

# Setup the LSST environment
setup_lsst_env() {
    echo "Setting up LSST stack..."
    cd "$LSST_STACK"
    source ./loadLSST.zsh
    setup lsst_distrib; setup obs_nickel
    cd "$OBS_NICKEL"
}

# ---
### Function to Run Calibrations

run_calibrations() {
    echo "--- Running calibration pipeline ---" | tee -a "$LOGS_DIR/calibs_$TS.log"
    
    # Check for and create Butler repository
    if [ ! -d "$REPO/butler.d" ]; then
        echo "Butler repository not found, creating a new one..." | tee -a "$LOGS_DIR/calibs_$TS.log"
        butler create "$REPO"
        butler register-instrument "$REPO" "$INSTRUMENT"
        butler ingest-raws "$REPO" "$RAWDIR" --transfer symlink --output-run "$RUN"
        butler define-visits "$REPO" Nickel
    else
        echo "Butler repository found. Ingesting new raw data..." | tee -a "$LOGS_DIR/calibs_$TS.log"
        butler ingest-raws "$REPO" "$RAWDIR" --transfer symlink --output-run "$RUN"
        butler define-visits "$REPO" Nickel
    fi

    # Create curated calibrations
    CURATED="Nickel/run/curated/$TS"
    echo "Writing curated calibrations to: $CURATED" | tee -a "$LOGS_DIR/calibs_$TS.log"
    butler write-curated-calibrations "$REPO" Nickel "$RUN" --collection "$CURATED"

    # Bias processing
    CP_RUN_BIAS="Nickel/run/cp_bias/$TS"
    echo "Running bias processing to: $CP_RUN_BIAS" | tee -a "$LOGS_DIR/calibs_$TS.log"
    pipetask run \
        -b "$REPO" \
        -i "$CURATED","$RUN" \
        -o "$CP_RUN_BIAS" \
        -p "$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml" \
        -d "instrument='Nickel' AND exposure.observation_type='bias'" \
        --register-dataset-types 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"
    butler certify-calibrations "$REPO" "$CP_RUN_BIAS" "$CURATED" bias \
        --begin-date 2020-01-01 --end-date 2030-01-01 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"

    # Flat processing
    CP_RUN_FLAT="Nickel/run/cp_flat/$TS"
    echo "Running flat processing to: $CP_RUN_FLAT" | tee -a "$LOGS_DIR/calibs_$TS.log"
    pipetask run \
        -b "$REPO" \
        -i "$CURATED","$RUN","$CP_RUN_BIAS" \
        -o "$CP_RUN_FLAT" \
        -p "$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml" \
        -c cpFlatIsr:doDark=False \
        -c cpFlatIsr:doOverscan=True \
        -d "instrument='Nickel' AND exposure.observation_type='flat'" \
        --register-dataset-types 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"

    # Defects processing (from flats)
    if butler query-datasets "$REPO" flat --collections "$CP_RUN_FLAT" &> /dev/null; then
        DEFECTS_RUN="Nickel/calib/defects/$TS"
        QA_DIR="$OBS_NICKEL/scripts/defects/qa_$TS"
        echo "Building defects from flats in $CP_RUN_FLAT -> $DEFECTS_RUN" | tee -a "$LOGS_DIR/calibs_$TS.log"
        python "$OBS_NICKEL"/scripts/defects/make_defects_from_flats.py \
            --repo "$REPO" \
            --collection "$CP_RUN_FLAT" \
            --manual-box 255 0 2 1025 \
            --manual-box 783 0 2 977 \
            --manual-box 1000 0 25 1024 \
            --register --ingest --defects-run "$DEFECTS_RUN" --plot --qa-dir "$QA_DIR" 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"
        butler collection-chain "$REPO" Nickel/calib/defects/current "$DEFECTS_RUN" --mode redefine 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"
    else
        echo "No 'flat' datasets found in $CP_RUN_FLAT; skipping defects build." | tee -a "$LOGS_DIR/calibs_$TS.log"
    fi

    # Unify calib chain
    CALIB_CHAIN="Nickel/calib/current"
    butler collection-chain "$REPO" "$CALIB_CHAIN" \
        "$CURATED" "$CP_RUN_BIAS" "$CP_RUN_FLAT" Nickel/calib/defects/current \
        --mode redefine 2>&1 | tee -a "$LOGS_DIR/calibs_$TS.log"
}

# ---
### Function to Run Reference Catalog Ingestion

run_refcats() {
    echo "--- Running reference catalog ingestion ---" | tee -a "$LOGS_DIR/refcats_$TS.log"
    cd "$REFCAT_REPO"

    # Gaia DR3
    echo "Processing Gaia DR3..." | tee -a "$LOGS_DIR/refcats_$TS.log"
    convertReferenceCatalog data/gaia-refcat/ scripts/gaia_dr3_config.py ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv &> convert-gaia.log
    butler register-dataset-type "$REPO" gaia_dr3_20250728 SimpleCatalog htm7 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"
    butler ingest-files -t direct "$REPO" gaia_dr3_20250728 refcats/gaia_dr3_20250728 data/gaia-refcat/filename_to_htm.ecsv 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"
    butler collection-chain "$REPO" --mode extend refcats refcats/gaia_dr3_20250728 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"

    # PS1 DR2
    echo "Processing PS1 DR2..." | tee -a "$LOGS_DIR/refcats_$TS.log"
    convertReferenceCatalog data/ps1-refcat/ scripts/ps1_config.py ./data/ps1_all_cones/merged_ps1_cones.csv &> convert-ps1.log
    butler register-dataset-type "$REPO" panstarrs1_dr2_20250730 SimpleCatalog htm7 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"
    butler ingest-files -t direct "$REPO" panstarrs1_dr2_20250730 refcats/panstarrs1_dr2_20250730 data/ps1-refcat/filename_to_htm.ecsv 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"
    butler collection-chain "$REPO" --mode extend refcats refcats/panstarrs1_dr2_20250730 2>&1 | tee -a "$LOGS_DIR/refcats_$TS.log"
}

# ---
### Function to Run `processCcd`

run_process_ccd() {
    echo "--- Running ProcessCcd pipeline ---" | tee -a "$LOGS_DIR/processCcd_$TS.log"
    cd "$OBS_NICKEL"
    PIPE="$OBS_NICKEL/pipelines/ProcessCcd.yaml"
    
    # Use different output names depending on whether we re-ran calibs
    if [ "$SKIP_CALIBS" = true ]; then
        PROCESS_CCD_RUN="Nickel/run/processCcd/reuseCalibs_$(date +%Y%m%dT%H%M%S)"
        echo "Using existing calibrations." | tee -a "$LOGS_DIR/processCcd_$TS.log"
    else
        PROCESS_CCD_RUN="Nickel/run/processCcd/$TS"
    fi

    echo "Science processing to: $PROCESS_CCD_RUN" | tee -a "$LOGS_DIR/processCcd_$TS.log"

    # The main pipetask command
    pipetask run \
        -b "$REPO" \
        -i "$RUN","Nickel/calib/current","refcats" \
        -o "$PROCESS_CCD_RUN" \
        -p "$PIPE#processCcd" \
        -d "instrument='Nickel' AND exposure.observation_type='science' AND NOT (exposure IN (${BAD}))" \
        --register-dataset-types 2>&1 | tee -a "$LOGS_DIR/processCcd_$TS.log"
}

# ---
### Main Execution

setup_lsst_env

if [ "$SKIP_CALIBS" = false ]; then
    run_calibrations
fi

if [ "$SKIP_REFCATS" = false ]; then
    run_refcats
fi

run_process_ccd

echo "=== Pipeline run finished ===" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"
echo "Check individual log files in: $LOGS_DIR" | tee -a "$LOGS_DIR/full_pipeline_$TS.log"