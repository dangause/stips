#!/usr/bin/env bash
# 05_build_template.sh — Download archival data for a field to build DIA templates
#
# Usage:
#   ./scripts/05_build_template.sh --ra 349.993 --dec -5.1656 --radius 0.5 \
#       --before 20201201 --output-tag template_2020wnt
#
# This script:
# 1. Queries the Lick Archive for all observations within a radius of RA/Dec
# 2. Filters for observations before a cutoff date (to exclude transient)
# 3. Downloads those observations
# 4. Ingests them for template building

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

########## CLI ##########
RA=""
DEC=""
RADIUS="0.5"  # degrees, default ~30 arcmin
BEFORE=""     # YYYYMMDD - only download observations before this date
OUTPUT_TAG=""
HELP=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ra) RA="${2:-}"; shift 2;;
    --dec) DEC="${2:-}"; shift 2;;
    --radius) RADIUS="${2:-}"; shift 2;;
    --before) BEFORE="${2:-}"; shift 2;;
    --output-tag) OUTPUT_TAG="${2:-}"; shift 2;;
    -h|--help) HELP=true; shift;;
    *) echo "Unknown arg: $1"; exit 2;;
  esac
done

if [[ "$HELP" == true ]] || [[ -z "$RA" ]] || [[ -z "$DEC" ]] || [[ -z "$BEFORE" ]] || [[ -z "$OUTPUT_TAG" ]]; then
  cat <<USAGE
Usage: $0 --ra RA --dec DEC --before YYYYMMDD --output-tag TAG [options]

Build a DIA template by downloading archival observations of a field.

Required:
  --ra RA              Right Ascension in decimal degrees
  --dec DEC            Declination in decimal degrees
  --before YYYYMMDD    Only download observations before this date (pre-transient)
  --output-tag TAG     Tag for organizing downloads (e.g., template_2020wnt)

Optional:
  --radius DEG         Search radius in degrees (default: 0.5 = ~30 arcmin)
  -h, --help           Show this help

Examples:
  # Build template for SN 2020wnt field (pre-discovery)
  $0 --ra 349.993 --dec -5.1656 --before 20201201 --output-tag template_2020wnt

  # Build template for field with custom radius
  $0 --ra 349.993 --dec -5.1656 --before 20201201 --radius 1.0 --output-tag my_template

Environment variables (from .env):
  RAW_PARENT_DIR      Destination for raw data downloads
  LICK_ARCHIVE_DIR    Path to lick_searchable_archive repo
  LICK_ARCHIVE_URL    Archive API URL
USAGE
  exit 0
fi

########## VALIDATION ##########
if [[ -z "$RAW_PARENT_DIR" ]]; then
  echo "ERROR: RAW_PARENT_DIR not set in .env" >&2
  exit 2
fi

# Python path
CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
PYTHON=/opt/anaconda3/envs/${CONDA_ENV}/bin/python

# Check if lick_archive is available
if ! $PYTHON -c "import lick_archive" 2>/dev/null; then
  if [[ -z "$LICK_ARCHIVE_DIR" ]]; then
    echo "ERROR: lick_archive not installed and LICK_ARCHIVE_DIR not set" >&2
    exit 2
  fi
  export PYTHONPATH="${LICK_ARCHIVE_DIR}:${PYTHONPATH:-}"
fi

########## SETUP ##########
TEMPLATE_DIR="${RAW_PARENT_DIR}/templates/${OUTPUT_TAG}"
mkdir -p "$TEMPLATE_DIR"

echo "=== [build_template] Building template for field ==="
echo "Target: RA=$RA, Dec=$DEC"
echo "Search radius: ${RADIUS} degrees"
echo "Date cutoff: Before $BEFORE"
echo "Output: $TEMPLATE_DIR"
echo ""

########## QUERY & DOWNLOAD ##########
# Create a Python script to query by coordinates and download
$PYTHON - <<PYEOF
import sys
from pathlib import Path
from datetime import datetime

# Import lick_archive client
from lick_archive.client.lick_archive_client import LickArchiveClient, QueryTerm
from astropy.coordinates import Angle

# Configuration
archive_url = "${LICK_ARCHIVE_URL}"
ra = ${RA}
dec = ${DEC}
radius = ${RADIUS}
before_date = "${BEFORE}"
output_dir = Path("${TEMPLATE_DIR}")
instrument = "NICKEL_DIR"

print(f"[INFO] Querying archive for coordinates: RA={ra}, Dec={dec}, radius={radius} deg")

# Create coordinate query
coord_dict = {
    "ra": Angle(ra, unit="deg"),
    "dec": Angle(dec, unit="deg"),
    "radius": Angle(radius, unit="deg")
}

# Set up client with rate limiting
client = LickArchiveClient(
    archive_url,
    rate_limit_delay=0.5,
    retry_max_time=300,
    retry_max_delay=60
)

# Query by coordinates
coord_term = QueryTerm(field="coord", value=coord_dict)
filters = {"instrument": instrument}

# Get all results
count, results, _, next_url = client.query(
    coord_term,
    filters=filters,
    results=["filename", "object", "obs_date"],
    page=1,
    page_size=1000
)

print(f"[INFO] Found {count} total observations in archive")

# Filter by date (before cutoff)
cutoff = datetime.strptime(before_date, "%Y%m%d")
filtered_results = []

for row in results:
    obs_date_str = row.get("obs_date", "")
    if obs_date_str:
        try:
            # Parse ISO format: "2020-12-01T12:00:00-08:00"
            obs_date = datetime.fromisoformat(obs_date_str.replace("Z", "+00:00"))
            obs_date_local = obs_date.replace(tzinfo=None)  # Remove timezone for comparison

            if obs_date_local < cutoff:
                filtered_results.append(row)
        except Exception as e:
            print(f"[WARN] Could not parse date for {row.get('filename')}: {obs_date_str}")

print(f"[INFO] {len(filtered_results)} observations before {before_date}")

if len(filtered_results) == 0:
    print("[ERROR] No observations found before cutoff date")
    sys.exit(1)

# Download files
downloaded = 0
skipped = 0
errors = 0

for row in filtered_results:
    filename = row.get("filename")
    if not filename:
        continue

    rel_path = Path(filename)
    dest = output_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"[SKIP] {filename}")
        skipped += 1
        continue

    try:
        print(f"[DOWNLOAD] {filename}")
        ok = client.download(filename, dest)
        if ok:
            downloaded += 1
        else:
            errors += 1
    except Exception as e:
        print(f"[ERROR] Failed to download {filename}: {e}")
        errors += 1

print(f"\n[SUMMARY] Downloaded: {downloaded}, Skipped: {skipped}, Errors: {errors}")
print(f"[OUTPUT] Template data in: {output_dir}")

sys.exit(0 if errors == 0 else 1)
PYEOF

RESULT=$?

if [[ $RESULT -eq 0 ]]; then
  echo ""
  echo "=== [build_template] SUCCESS ==="
  echo "Template data: $TEMPLATE_DIR"
  echo ""
  echo "Next steps:"
  echo "1. Ingest template data into Butler"
  echo "2. Run calibs and science processing on template data"
  echo "3. Build template coadd"
  echo "4. Use template for DIA on science images"
else
  echo ""
  echo "=== [build_template] FAILED ===" >&2
  echo "Check the log above for errors" >&2
  exit 1
fi
