#!/usr/bin/env bash
# Nickel reduction pipeline — persistent repo, nightly certification

# set -euo pipefail

############################
# CLI parsing
############################
NIGHT="${NIGHT:-}"   # allow env override
BAD_EXPOSURES=""     # exposure IDs (integers)
BAD_EXPOSURES_FILE=""
BAD_OBSIDS=""        # OBSNUM strings (e.g., 1052)
BAD_OBSIDS_FILE=""

usage() {
  cat <<USAGE
Usage: $0 --night YYYYMMDD [--bad EXPOSURE_IDS] [--bad-file FILE] [--bad-obs OBSNUMS] [--bad-obs-file FILE]

Options:
  -n, --night          Night tag in YYYYMMDD format (required unless NIGHT env var set)
      --bad            Comma-separated exposure IDs to exclude (e.g. "88991050,88991052")
      --bad-file       Path to file with exposure IDs to exclude (one per line; comments with '#')
      --bad-obs        Comma-separated OBSNUMs to exclude (e.g. "1050,1052")
      --bad-obs-file   Path to file with OBSNUMs to exclude (one per line; comments with '#')
  -h, --help           Show this help

Examples:
  $0 --night 20240624
  $0 -n 20240624 --bad "88991050,88991052"
  $0 -n 20240624 --bad-obs "1050,1052"
  $0 -n 20240624 --bad-file bad_exposures.txt --bad-obs-file bad_obs.txt
  NIGHT=20240512 $0
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)        NIGHT="${2:-}"; shift 2;;
    --bad)             BAD_EXPOSURES="${2:-}"; shift 2;;
    --bad-file)        BAD_EXPOSURES_FILE="${2:-}"; shift 2;;
    --bad-obs)         BAD_OBSIDS="${2:-}"; shift 2;;
    --bad-obs-file)    BAD_OBSIDS_FILE="${2:-}"; shift 2;;
    -h|--help)         usage; exit 0;;
    *) echo "Unknown argument: $1"; usage; exit 2;;
  esac
done

if [[ -z "${NIGHT}" ]]; then
  echo "ERROR: Night not provided. Use --night YYYYMMDD or set NIGHT env var."
  usage
  exit 2
fi

########## USER PATHS ##########
RAWDIR="/Users/dangause/Developer/lick/data/${NIGHT}/raw"                                         # raw data directory
REPO="/Users/dangause/Developer/lick/lsst/data/nickel/repo"                                      # persistent Butler repo
OBS_NICKEL="/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/packages/obs_nickel"   # obs_nickel package directory
REFCAT_REPO="/Users/dangause/Developer/lick/lsst/lsst_stack/stack/refcats"                       # refcat working repo
STACK_DIR="/Users/dangause/Developer/lick/lsst/lsst_stack"                                        # lsst_stack (has loadLSST.zsh)

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

########## REF CATS (concise & idempotent) ##########
cd "$REFCAT_REPO"

# Latest converted outputs from scripts/convert_refcats.py
GAIA_DIR=$(ls -d data/gaia-refcat-* 2>/dev/null | sort -V | tail -n1)
PS1_DIR=$(ls -d data/ps1-refcat-*  2>/dev/null | sort -V | tail -n1)

[[ -n "$GAIA_DIR" && -n "$PS1_DIR" ]] || {
  echo "[refcats] No converted outputs; run: python scripts/convert_refcats.py"; exit 2; }

GAIA_DT="gaia_dr3";            GAIA_MAP="${GAIA_DIR}/filename_to_htm.ecsv"
PS1_DT="panstarrs1_dr2";       PS1_MAP="${PS1_DIR}/filename_to_htm.ecsv"
GAIA_RUN="refcats/${GAIA_DT}_${GAIA_DIR##*-}"
PS1_RUN="refcats/${PS1_DT}_${PS1_DIR##*-}"

[[ -s "$GAIA_MAP" ]] || { echo "[refcats] GAIA map not found: $GAIA_MAP"; exit 2; }
[[ -s "$PS1_MAP"  ]] || { echo "[refcats] PS1  map not found: $PS1_MAP";  exit 2; }

echo "[refcats][GAIA] Registering dataset type: $GAIA_DT"
butler register-dataset-type "$REPO" "$GAIA_DT" SimpleCatalog htm7 || true
echo "[refcats][PS1 ] Registering dataset type: $PS1_DT"
butler register-dataset-type "$REPO" "$PS1_DT" SimpleCatalog htm7 || true

# Ingest only if the RUN collection doesn't already exist
if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$GAIA_RUN"; then
  echo "[refcats][GAIA] Ingest → $GAIA_RUN"
  butler ingest-files -t direct "$REPO" "$GAIA_DT" "$GAIA_RUN" "$GAIA_MAP"
else
  echo "[refcats][GAIA] Skip ingest (exists) → $GAIA_RUN"
fi

if ! butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$PS1_RUN"; then
  echo "[refcats][PS1 ] Ingest → $PS1_RUN"
  butler ingest-files -t direct "$REPO" "$PS1_DT" "$PS1_RUN" "$PS1_MAP"
else
  echo "[refcats][PS1 ] Skip ingest (exists) → $PS1_RUN"
fi

# Build/refresh 'refcats' chain with whatever runs exist
children=()
butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$GAIA_RUN" && children+=("$GAIA_RUN")
butler query-collections "$REPO" | awk '{print $1}' | grep -qx "$PS1_RUN"  && children+=("$PS1_RUN")

if (( ${#children[@]} )); then
  echo "[refcats] Chain 'refcats' = [${children[*]}]"
  butler collection-chain "$REPO" refcats "${children[@]}" --mode redefine
  butler query-collections "$REPO" | grep -E '^refcats$|^  refcats/' || true
else
  echo "[refcats] Nothing to chain."
fi


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

# -------------------------------------------------
# Build the exclusion predicate from CLI/file inputs
# -------------------------------------------------
# Normalize comma-separated strings -> newline, strip comments/spaces, keep digits only.
norm_csv_to_lines() {
  # read from STDIN
  tr -cs '0-9,\n' '\n' | sed 's/^0\+//' | sed '/^$/d'
}
norm_file_to_lines() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  sed 's/#.*//' "$f" | tr -cs '0-9,\n' '\n' | sed 's/^0\+//' | sed '/^$/d'
}

BAD_EXP_CSV=""
BAD_OBS_CSV=""

# From --bad (exposure IDs)
if [[ -n "$BAD_EXPOSURES" ]]; then
  BAD_EXP_CSV="$(printf "%s" "$BAD_EXPOSURES" | norm_csv_to_lines | awk 'length($0)>=7' | sort -u | paste -sd, -)"
fi
# From --bad-file (exposure IDs)
if [[ -n "$BAD_EXPOSURES_FILE" && -f "$BAD_EXPOSURES_FILE" ]]; then
  ADD="$(norm_file_to_lines "$BAD_EXPOSURES_FILE" | awk 'length($0)>=7' | sort -u | paste -sd, -)"
  [[ -n "$ADD" ]] && BAD_EXP_CSV="${BAD_EXP_CSV:+$BAD_EXP_CSV,}$ADD"
fi

# From --bad-obs (OBSNUMs)
if [[ -n "$BAD_OBSIDS" ]]; then
  BAD_OBS_CSV="$(printf "%s" "$BAD_OBSIDS" | norm_csv_to_lines | awk 'length($0)>=1 && length($0)<=6' | sort -u | paste -sd, -)"
fi
# From --bad-obs-file (OBSNUMs)
if [[ -n "$BAD_OBSIDS_FILE" && -f "$BAD_OBSIDS_FILE" ]]; then
  ADD="$(norm_file_to_lines "$BAD_OBSIDS_FILE" | awk 'length($0)>=1 && length($0)<=6' | sort -u | paste -sd, -)"
  [[ -n "$ADD" ]] && BAD_OBS_CSV="${BAD_OBS_CSV:+$BAD_OBS_CSV,}$ADD"
fi

# Build the WHERE clause tail
BAD_EXPR=""
if [[ -n "$BAD_EXP_CSV" ]]; then
  BAD_EXPR+=" AND NOT (exposure IN (${BAD_EXP_CSV}))"
fi
if [[ -n "$BAD_OBS_CSV" ]]; then
  # quote each OBSNUM for SQL string comparison
  local_quoted="$(printf "%s\n" "$BAD_OBS_CSV" | tr ',' '\n' | sed "s/.*/'&'/" | paste -sd, -)"
  BAD_EXPR+=" AND NOT (exposure.obs_id IN (${local_quoted}))"
fi

if [[ -n "$BAD_EXP_CSV$BAD_OBS_CSV" ]]; then
  echo "[science] Excluding exposures: ${BAD_EXP_CSV:-<none>}  and OBSNUMs: ${BAD_OBS_CSV:-<none>}"
fi
# -------------------------------------------------

# sanity
butler query-collections "$REPO" | grep -E 'Nickel/calib/(current|defects/current)|^refcats$' || true

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
