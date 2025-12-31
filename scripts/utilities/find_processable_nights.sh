#!/usr/bin/env bash
#
# find_processable_nights.sh - Find nights with complete single-visit processing per band
#
# This script queries the Butler to find which nights have successfully completed
# single-visit processing (with single_visit_star_footprints) for each band.
# This is useful for determining which nights can be used for DIA processing.
#
# Usage:
#   ./find_processable_nights.sh --object 2020wnt --bands "v,r,i" --tract 1825
#

set -euo pipefail

[[ -f ".env" ]] && { set -a; source .env; set +a; }

OBJECT=""
BANDS="b,v,r,i"
TRACT=""
OUTPUT_DIR="scripts/config"

usage() {
  cat <<USAGE
Usage: $0 [OPTIONS]

Find nights with complete single-visit processing per band.

Options:
  --object NAME       Filter by target name (e.g., "2020wnt")
  --bands LIST        Comma-separated bands to check (default: "b,v,r,i")
  --tract TRACT       Filter by tract number
  --output-dir DIR    Output directory for night lists (default: scripts/config)
  -h, --help          Show this help

Examples:
  # Find all processable nights for 2020wnt
  $0 --object 2020wnt --bands "v,r,i" --tract 1825

  # Check all bands
  $0 --object 2020wnt

USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --object)       OBJECT="${2:-}"; shift 2;;
    --bands)        BANDS="${2:-}"; shift 2;;
    --tract)        TRACT="${2:-}"; shift 2;;
    --output-dir)   OUTPUT_DIR="${2:-}"; shift 2;;
    -h|--help)      usage;;
    *) echo "Unknown option: $1"; usage;;
  esac
done

[[ -z "${REPO:-}" ]] && { echo "ERROR: REPO not set"; exit 1; }
[[ -z "$OBJECT" ]] && { echo "ERROR: --object required"; exit 1; }

mkdir -p "$OUTPUT_DIR/$OBJECT"

echo "=== Finding processable nights for $OBJECT ==="
echo "Repository: $REPO"
echo "Bands: $BANDS"
[[ -n "$TRACT" ]] && echo "Tract: $TRACT"
echo

IFS=',' read -r -a BAND_ARRAY <<< "$BANDS"

for BAND in "${BAND_ARRAY[@]}"; do
  BAND="$(echo "$BAND" | tr -d '[:space:]')"
  [[ -z "$BAND" ]] && continue

  echo "=== Band: $BAND ==="

  # Build WHERE clause (note: single_visit_star_footprints doesn't have tract dimension)
  WHERE="instrument='Nickel' AND exposure.observation_type='science' AND exposure.target_name='$OBJECT' AND band='$BAND'"

  # Query for exposures with single_visit_star_footprints
  OUTPUT_FILE="$OUTPUT_DIR/$OBJECT/processable_nights_${BAND}.txt"

  butler query-datasets "$REPO" single_visit_star_footprints \
    --collections 'Nickel/runs/*' \
    --where "$WHERE" \
    2>/dev/null | \
    awk '{print $8}' | \
    grep -E '^[0-9]{8}$' | \
    sort -u > "$OUTPUT_FILE"

  COUNT=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
  echo "  Found $COUNT nights with complete processing"
  echo "  Output: $OUTPUT_FILE"

  if [[ $COUNT -gt 0 ]]; then
    echo "  Nights: $(head -5 "$OUTPUT_FILE" | tr '\n' ' ')..."
  fi
  echo
done

echo "=== Summary ==="
echo "Night lists created in: $OUTPUT_DIR/$OBJECT/"
ls -lh "$OUTPUT_DIR/$OBJECT"/processable_nights_*.txt
echo
echo "To use these with run_dia_multi_band.sh:"
echo "  ./scripts/pipeline/run_dia_multi_band.sh \\"
echo "    --template-nights $OUTPUT_DIR/$OBJECT/template_nights.txt \\"
echo "    --science-nights $OUTPUT_DIR/$OBJECT/processable_nights_v.txt \\"
echo "    --bands v --tract $TRACT --object $OBJECT"
