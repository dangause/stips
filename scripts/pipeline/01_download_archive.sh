#!/usr/bin/env bash
# 00_download_archive.sh — Download Nickel data from Lick Archive
#
# Usage:
#   ./scripts/00_download_archive.sh --night YYYYMMDD [options]

ENV_FILE="${ENV_FILE:-.env}"
EXTRA_ENV="${EXTRA_ENV:-}"

set -a
for f in $ENV_FILE $EXTRA_ENV; do
  [ -n "$f" ] && [ -f "$f" ] && source "$f"
done
set +a

########## CLI ##########
NIGHT=""
OVERWRITE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--night)
      NIGHT="${2:-}"
      shift 2
      ;;
    --overwrite)
      OVERWRITE=true
      shift
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    -h|--help)
      cat <<USAGE
Usage: $0 --night YYYYMMDD [options]

Download Nickel telescope data from the Lick Searchable Archive.

Required:
  -n, --night YYYYMMDD      Observing night to download

Options:
  --overwrite               Re-download files even if they exist
  -v, --verbose             Enable verbose output
  -h, --help                Show this help message

Environment variables (from .env):
  RAW_PARENT_DIR            Destination for raw data downloads
  LICK_ARCHIVE_DIR          Path to lick_searchable_archive repo
  LICK_ARCHIVE_URL          Archive API URL
  LICK_ARCHIVE_INSTR        Instrument filter (default: NICKEL)

Example:
  # Download all data for a night
  $0 --night 20201207

  # Re-download even if files exist
  $0 --night 20201207 --overwrite

The data will be downloaded to: \$RAW_PARENT_DIR/\${NIGHT}/raw/
USAGE
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      echo "Use --help for usage information" >&2
      exit 2
      ;;
  esac
done

# Validate required arguments
if [[ -z "$NIGHT" ]]; then
  echo "ERROR: --night is required" >&2
  exit 2
fi

if [[ -z "$RAW_PARENT_DIR" ]]; then
  echo "ERROR: RAW_PARENT_DIR not set in .env" >&2
  exit 2
fi

# Default to workspace copy if not explicitly set
if [[ -z "${LICK_ARCHIVE_DIR:-}" && -d "${OBS_NICKEL}/packages/lick_searchable_archive" ]]; then
  LICK_ARCHIVE_DIR="${OBS_NICKEL}/packages/lick_searchable_archive"
fi

# Use LSST Python environment (prefer current active Python)
CONDA_ENV="${LSST_CONDA_ENV_NAME:-lsst-scipipe-12.0.0}"
PYTHON="${LSST_PYTHON:-$(command -v python)}"
if [[ -z "$PYTHON" ]]; then
  PYTHON="/opt/anaconda3/envs/${CONDA_ENV}/bin/python"
fi
# Prefer lick_searchable_archive's venv when available (ensures client deps like tenacity are installed)
if [[ -n "${LICK_ARCHIVE_DIR:-}" && -x "${LICK_ARCHIVE_DIR}/.venv/bin/python" ]]; then
  PYTHON="${LICK_ARCHIVE_DIR}/.venv/bin/python"
fi

# Check if lick_archive is installed or LICK_ARCHIVE_DIR is set
if [[ -n "$LICK_ARCHIVE_DIR" ]]; then
  export PYTHONPATH="$LICK_ARCHIVE_DIR${PYTHONPATH:+:$PYTHONPATH}"
fi

if ! $PYTHON -c "import lick_archive" 2>/dev/null; then
  if [[ -z "$LICK_ARCHIVE_DIR" ]]; then
    echo "ERROR: lick_archive not installed and LICK_ARCHIVE_DIR not set" >&2
    echo "" >&2
    echo "Option 1 (Recommended): Install into LSST conda environment" >&2
    echo "  ${PYTHON%/python}/pip install -e ~/Developer/lick/lick_searchable_archive" >&2
    echo "" >&2
    echo "Option 2: Set LICK_ARCHIVE_DIR in .env (already configured)" >&2
    echo "  LICK_ARCHIVE_DIR=~/Developer/lick/lick_searchable_archive" >&2
    exit 2
  fi
fi

########## SETUP ##########
echo "=== [00_download_archive] night=${NIGHT} ==="
echo ""

# Build command
FETCH_ARGS=(--night "$NIGHT" --raw-root "$RAW_PARENT_DIR")

if [[ "$OVERWRITE" == true ]]; then
  FETCH_ARGS+=(--overwrite)
fi

# Export environment for Python script
export RAW_PARENT_DIR
export LICK_ARCHIVE_URL
export LICK_ARCHIVE_INSTR

# Add lick_archive to PYTHONPATH if not installed
if ! $PYTHON -c "import lick_archive" 2>/dev/null; then
  export LICK_ARCHIVE_DIR
  export PYTHONPATH="${LICK_ARCHIVE_DIR}:${PYTHONPATH:-}"
  echo "Using lick_archive from: $LICK_ARCHIVE_DIR"
else
  echo "Using installed lick_archive package"
fi

# Resolve CLI entrypoint
FETCH_CMD=(obsn-archive-fetch-night)
PYTHON_BIN="$(dirname "$PYTHON")"
if [[ -x "${PYTHON_BIN}/obsn-archive-fetch-night" ]]; then
  FETCH_CMD=("${PYTHON_BIN}/obsn-archive-fetch-night")
elif ! command -v obsn-archive-fetch-night >/dev/null 2>&1; then
  echo "ERROR: obsn-archive-fetch-night not found. Install obs-nickel-data-tools or activate its env." >&2
  exit 2
fi

# Run download script
echo "Downloading data from Lick Archive..."
echo "Archive: $LICK_ARCHIVE_URL"
echo "Instrument: ${LICK_ARCHIVE_INSTR:-NICKEL}"
echo "Destination: $RAW_PARENT_DIR/$NIGHT/raw/"
echo ""

if "${FETCH_CMD[@]}" "${FETCH_ARGS[@]}"; then
  echo ""
  echo "=== [00_download_archive] SUCCESS ==="
  echo "Night:  $NIGHT"
  echo "Output: $RAW_PARENT_DIR/$NIGHT/raw/"
  echo ""
  echo "Next step: Run calibration pipeline"
  echo "  ./scripts/10_calibs.sh --night $NIGHT"
  echo ""
else
  echo ""
  echo "=== [00_download_archive] FAILED ===" >&2
  echo "Check the log above for errors" >&2
  exit 1
fi
