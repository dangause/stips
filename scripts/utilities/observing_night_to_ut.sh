#!/usr/bin/env bash
#
# observing_night_to_ut.sh - Convert observing night dates to UT day_obs dates
#
# Usage:
#   ./scripts/utilities/observing_night_to_ut.sh nights_file.txt [--object TARGET_NAME]
#
# This script takes a file with observing night dates (local date when the night starts)
# and queries the butler to find the actual UT day_obs values that contain data.
#
# Why this is needed:
# - Astronomers refer to nights by the local date when observations BEGIN
# - FITS headers record UT date when each exposure is taken
# - For California (UTC-8), observations after ~4pm local time have NEXT day's UT date
# - Butler uses day_obs (UT date) internally, so queries must use UT dates
#
# Example:
#   Observing night: 2021-07-21 (local date)
#   Observations taken: 2021-07-21 ~8pm-4am local (2021-07-22 04:00 - 2021-07-22 12:00 UT)
#   Butler day_obs: 20210722 (UT date)
#

set -euo pipefail

NIGHTS_FILE="${1:-}"
OBJECT_FILTER=""
VERIFY_ONLY=false

usage() {
  cat <<USAGE
Usage: $0 NIGHTS_FILE [OPTIONS]

Convert observing night dates to UT day_obs dates by querying butler.

Arguments:
  NIGHTS_FILE       File with observing nights (YYYYMMDD, one per line)

Options:
  --object NAME     Only include nights with this target_name
  --verify-only     Only check which nights have data, don't output UT dates
  -h, --help        Show this help

Output:
  Prints UT dates (day_obs) to stdout, one per line
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --object) OBJECT_FILTER="$2"; shift 2;;
    --verify-only) VERIFY_ONLY=true; shift 1;;
    -h|--help) usage;;
    -*) echo "Unknown option: $1"; usage;;
    *) NIGHTS_FILE="$1"; shift 1;;
  esac
done

[[ -z "$NIGHTS_FILE" ]] && usage
[[ ! -f "$NIGHTS_FILE" ]] && { echo "ERROR: File not found: $NIGHTS_FILE"; exit 1; }
[[ -z "${REPO:-}" ]] && { echo "ERROR: REPO not set. Source your .env file first."; exit 1; }

# Read nights, skipping comments and empty lines
readarray -t OBSERVING_NIGHTS < <(grep -v '^#' "$NIGHTS_FILE" | grep -v '^[[:space:]]*$' | tr -d '[:space:]')

for OBS_NIGHT in "${OBSERVING_NIGHTS[@]}"; do
  # Check both the observing night date and the next day
  # (most Nickel data will be on the next UT day)
  if [[ "$OSTYPE" == "darwin"* ]]; then
    NEXT_DAY=$(date -j -v+1d -f "%Y%m%d" "$OBS_NIGHT" "+%Y%m%d" 2>/dev/null || echo "")
  else
    NEXT_DAY=$(date -d "$OBS_NIGHT + 1 day" "+%Y%m%d" 2>/dev/null || echo "")
  fi

  for UT_DATE in "$OBS_NIGHT" "$NEXT_DAY"; do
    [[ -z "$UT_DATE" ]] && continue

    # Build WHERE clause
    WHERE="instrument='Nickel' AND exposure.day_obs=${UT_DATE}"
    if [[ -n "$OBJECT_FILTER" ]]; then
      WHERE="${WHERE} AND exposure.target_name='${OBJECT_FILTER}'"
    fi

    # Check if this UT date has data
    if butler query-dimension-records "$REPO" exposure \
        --where "$WHERE" 2>/dev/null | grep -q "^    Nickel"; then

      if [[ "$VERIFY_ONLY" == "true" ]]; then
        echo "Observing night $OBS_NIGHT -> UT date $UT_DATE ✓"
      else
        echo "$UT_DATE"
      fi
      break  # Found data for this observing night
    fi
  done
done
