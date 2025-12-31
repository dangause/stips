#!/usr/bin/env bash
#
# radec_to_tract.sh - Convert RA/Dec to tract number(s)
#
# Usage:
#   ./radec_to_tract.sh RA DEC [SKYMAP]
#
# Example:
#   ./radec_to_tract.sh 56.66 43.23 nickelRings-v1
#

set -euo pipefail

RA="${1:-}"
DEC="${2:-}"
SKYMAP="${3:-nickelRings-v1}"

if [[ -z "$RA" ]] || [[ -z "$DEC" ]]; then
  echo "Usage: $0 RA DEC [SKYMAP]" >&2
  echo "Example: $0 56.66 43.23 nickelRings-v1" >&2
  exit 1
fi

[[ -z "${REPO:-}" ]] && { echo "ERROR: REPO not set" >&2; exit 1; }

# Query butler for tracts overlapping this coordinate
# Output only the tract number(s)
butler query-dimension-records "$REPO" skymap \
  --where "skymap='$SKYMAP' AND POINT($RA, $DEC) OVERLAPS region" \
  2>/dev/null | \
  awk '/^[[:space:]]+'"$SKYMAP"'/ {print $2}' | \
  sort -u
