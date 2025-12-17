#!/usr/bin/env bash
# run_dia_for_object.sh — Complete DIA workflow for a specific object
#
# This is a master script that orchestrates the complete DIA workflow:
# 1. Download pre-transient archival data for template
# 2. Process template data through calibs + science
# 3. Build coadded template
# 4. Download science night data
# 5. Process science night
# 6. Run DIA (science - template)
# 7. Extract light curve

set -a
source .env
set +a

########## CLI ##########
OBJECT_NAME=""
RA=""
DEC=""
BEFORE_DATE=""
SCIENCE_NIGHT=""
RADIUS="0.5"
JOBS=1
SKIP_DOWNLOAD=false
SKIP_TEMPLATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --object) OBJECT_NAME="${2:-}"; shift 2;;
    --ra) RA="${2:-}"; shift 2;;
    --dec) DEC="${2:-}"; shift 2;;
    --before) BEFORE_DATE="${2:-}"; shift 2;;
    --science-night) SCIENCE_NIGHT="${2:-}"; shift 2;;
    --radius) RADIUS="${2:-}"; shift 2;;
    --jobs) JOBS="${2:-}"; shift 2;;
    --skip-download) SKIP_DOWNLOAD=true; shift;;
    --skip-template) SKIP_TEMPLATE=true; shift;;
    -h|--help)
      cat <<USAGE
Usage: $0 --object NAME --ra RA --dec DEC --before YYYYMMDD --science-night YYYYMMDD [options]

Complete DIA workflow for a specific transient object.

Required:
  --object NAME         Object name (e.g., 2020wnt)
  --ra RA               Right Ascension in decimal degrees
  --dec DEC             Declination in decimal degrees
  --before YYYYMMDD     Date cutoff for template (pre-transient observations only)
  --science-night YYYYMMDD  Night with transient to analyze

Optional:
  --radius DEG          Search radius for template in degrees (default: 0.5)
  --jobs N              Number of parallel jobs (default: 1)
  --skip-download       Skip downloading data (assume already downloaded)
  --skip-template       Skip template processing (assume already processed)
  -h, --help            Show this help

Example - Complete workflow for SN 2020wnt:
  $0 --object 2020wnt \\
     --ra 349.993 \\
     --dec -5.1656 \\
     --before 20201201 \\
     --science-night 20201208 \\
     --jobs 4

This will:
1. Download archival pre-transient data (before 2020-12-01)
2. Process template data through calibs + science pipeline
3. Build coadded template
4. Download science night data (2020-12-08)
5. Process science night
6. Run difference imaging
7. Extract light curve for the object
USAGE
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

# Validation
[[ -n "$OBJECT_NAME" ]] || { echo "ERROR: --object required"; exit 2; }
[[ -n "$RA" ]] || { echo "ERROR: --ra required"; exit 2; }
[[ -n "$DEC" ]] || { echo "ERROR: --dec required"; exit 2; }
[[ -n "$BEFORE_DATE" ]] || { echo "ERROR: --before required"; exit 2; }
[[ -n "$SCIENCE_NIGHT" ]] || { echo "ERROR: --science-night required"; exit 2; }

TEMPLATE_TAG="template_${OBJECT_NAME}"

########## LSST STACK SETUP ##########
# Load LSST environment for butler commands
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true
cd - >/dev/null

echo "============================================================"
echo "DIA Workflow for ${OBJECT_NAME}"
echo "============================================================"
echo "Object:         $OBJECT_NAME"
echo "Coordinates:    RA=$RA, Dec=$DEC"
echo "Template from:  Before $BEFORE_DATE"
echo "Science night:  $SCIENCE_NIGHT"
echo "Jobs:           $JOBS"
echo "============================================================"
echo ""

########## STEP 1: Download Template Data ##########
if [[ "$SKIP_DOWNLOAD" == false ]] && [[ "$SKIP_TEMPLATE" == false ]]; then
  echo "STEP 1: Downloading pre-transient archival data for template..."
  ./scripts/05_build_template.sh \
    --ra "$RA" \
    --dec "$DEC" \
    --radius "$RADIUS" \
    --before "$BEFORE_DATE" \
    --output-tag "$TEMPLATE_TAG"

  if [[ $? -ne 0 ]]; then
    echo "ERROR: Template download failed" >&2
    exit 1
  fi
  echo ""
fi

########## STEP 2: Process Template Data ##########
if [[ "$SKIP_TEMPLATE" == false ]]; then
  echo "STEP 2: Processing template data through calibs + science..."
  ./scripts/06_process_template.sh \
    --template-tag "$TEMPLATE_TAG" \
    --jobs "$JOBS"

  if [[ $? -ne 0 ]]; then
    echo "ERROR: Template processing failed" >&2
    exit 1
  fi

  # Extract the science run collection from output
  SCIENCE_RUN=$(butler query-collections "$REPO" "Nickel/templates/${TEMPLATE_TAG}/science/*" | awk '{print $1}' | grep -v "^Name$" | tail -1)
  if [[ -z "$SCIENCE_RUN" ]]; then
    echo "ERROR: Could not find science run collection" >&2
    exit 1
  fi
  echo "Found science run: $SCIENCE_RUN"
  echo ""
fi

########## STEP 3: Build Coadded Template ##########
if [[ "$SKIP_TEMPLATE" == false ]]; then
  echo "STEP 3: Building coadded template..."
  ./scripts/07_build_coadd_template.sh \
    --template-tag "$TEMPLATE_TAG" \
    --science-run "$SCIENCE_RUN" \
    --jobs "$JOBS"

  if [[ $? -ne 0 ]]; then
    echo "ERROR: Template coadd failed" >&2
    exit 1
  fi
  echo ""
fi

TEMPLATE_COLLECTION="Nickel/templates/${TEMPLATE_TAG}"

########## STEP 4: Download Science Night Data ##########
if [[ "$SKIP_DOWNLOAD" == false ]]; then
  echo "STEP 4: Downloading science night data..."
  ./scripts/00_download_archive.sh --night "$SCIENCE_NIGHT"

  if [[ $? -ne 0 ]]; then
    echo "ERROR: Science night download failed" >&2
    exit 1
  fi
  echo ""
fi

########## STEP 5: Process Science Night ##########
echo "STEP 5: Processing science night through calibs..."
./scripts/10_calibs.sh --night "$SCIENCE_NIGHT"

if [[ $? -ne 0 ]]; then
  echo "ERROR: Calibs failed" >&2
  exit 1
fi

echo "STEP 5b: Processing science night..."
./scripts/20_science.sh --night "$SCIENCE_NIGHT" --jobs "$JOBS"

if [[ $? -ne 0 ]]; then
  echo "ERROR: Science processing failed" >&2
  exit 1
fi
echo ""

########## STEP 6: Run DIA ##########
echo "STEP 6: Running difference imaging..."
./scripts/40_diff_imaging.sh \
  --night "$SCIENCE_NIGHT" \
  --template "$TEMPLATE_COLLECTION" \
  --object "$OBJECT_NAME" \
  --jobs "$JOBS"

if [[ $? -ne 0 ]]; then
  echo "ERROR: DIA failed" >&2
  exit 1
fi
echo ""

########## STEP 7: Extract Light Curve ##########
echo "STEP 7: Extracting light curve..."
echo "Light curve data should be in Butler DIA outputs"
echo "Use Butler to query diaSource catalogs for your object"
echo ""

echo "============================================================"
echo "DIA Workflow Complete!"
echo "============================================================"
echo "Object:             $OBJECT_NAME"
echo "Template:           $TEMPLATE_COLLECTION"
echo "Science night:      $SCIENCE_NIGHT"
echo ""
echo "Next steps:"
echo "1. Query DIA sources from Butler"
echo "2. Match sources to object coordinates"
echo "3. Extract light curve photometry"
echo "============================================================"
