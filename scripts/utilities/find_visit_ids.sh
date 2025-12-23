#!/usr/bin/env bash
# find_visit_ids.sh - Find visit IDs for a specific night

set -a
source .env
set +a

NIGHT="${1:-20240624}"
BAND="${2:-r}"

echo "Finding visits for night=$NIGHT band=$BAND..."
echo ""

# Setup LSST
cd "$STACK_DIR"
source loadLSST.zsh
setup lsst_distrib
setup obs_nickel || true

# Find the processCcd collection for this night
PROC_COLL=$(butler query-collections "$REPO" \
  | awk '{print $1}' \
  | grep -E "^Nickel/runs/${NIGHT}/processCcd/[0-9TZ]+(/run)?$" \
  | tail -n1)

if [[ -z "$PROC_COLL" ]]; then
  echo "ERROR: No processCcd collection found for night $NIGHT"
  echo ""
  echo "Available nights:"
  butler query-collections "$REPO" | grep "processCcd" | grep -oE "[0-9]{8}" | sort -u
  exit 1
fi

echo "Collection: $PROC_COLL"
echo ""

# Query for visits
echo "Visits in $BAND-band:"
butler query-dimension-records "$REPO" visit \
  --collections "$PROC_COLL" \
  --where "instrument='Nickel' AND band='$BAND'" \
  | grep -E "^[0-9]+" \
  | awk '{print $1}' \
  | sort -n

echo ""
echo "To use a visit, export it:"
echo "  export TEST_VISIT=XXXXXXXX"
