#!/usr/bin/env bash
#
# update_exposure_coords_sql.sh - Directly update Butler SQLite database to fix coordinates
#
# WARNING: This modifies the Butler registry database directly!
# Make a backup first: cp $REPO/gen3.sqlite3 $REPO/gen3.sqlite3.backup
#
# Usage:
#   ./update_exposure_coords_sql.sh 2020wnt 56.66 43.23
#

set -euo pipefail

[[ -f ".env" ]] && { set -a; source .env; set +a; }

OBJECT="${1:-}"
CORRECT_RA="${2:-}"
CORRECT_DEC="${3:-}"

if [[ -z "$OBJECT" ]] || [[ -z "$CORRECT_RA" ]] || [[ -z "$CORRECT_DEC" ]]; then
  echo "Usage: $0 OBJECT_NAME CORRECT_RA CORRECT_DEC"
  echo "Example: $0 2020wnt 56.66 43.23"
  exit 1
fi

[[ -z "${REPO:-}" ]] && { echo "ERROR: REPO not set"; exit 1; }

DB_FILE="$REPO/gen3.sqlite3"

if [[ ! -f "$DB_FILE" ]]; then
  echo "ERROR: Database not found at $DB_FILE"
  echo "This script only works with SQLite Butler repositories"
  exit 1
fi

echo "=== Updating coordinates for $OBJECT in Butler database ==="
echo "Repository: $REPO"
echo "Database: $DB_FILE"
echo "New coordinates: RA=$CORRECT_RA°, Dec=$CORRECT_DEC°"
echo

# Make backup
BACKUP_FILE="$DB_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo "Creating backup: $BACKUP_FILE"
cp "$DB_FILE" "$BACKUP_FILE"
echo

# First, show what will be changed
echo "Exposures that will be updated:"
sqlite3 "$DB_FILE" <<EOF
SELECT
  id,
  day_obs,
  physical_filter,
  tracking_ra,
  tracking_dec,
  target_name
FROM exposure
WHERE instrument = 'Nickel'
  AND target_name = '$OBJECT'
  AND (
    ABS(tracking_ra - $CORRECT_RA) > 5.0
    OR ABS(tracking_dec - $CORRECT_DEC) > 5.0
  );
EOF

echo
read -p "Update these exposures? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborted."
  exit 0
fi

# Perform the update
echo "Updating database..."
sqlite3 "$DB_FILE" <<EOF
UPDATE exposure
SET tracking_ra = $CORRECT_RA,
    tracking_dec = $CORRECT_DEC
WHERE instrument = 'Nickel'
  AND target_name = '$OBJECT'
  AND (
    ABS(tracking_ra - $CORRECT_RA) > 5.0
    OR ABS(tracking_dec - $CORRECT_DEC) > 5.0
  );
EOF

# Show results
UPDATED=$(sqlite3 "$DB_FILE" "SELECT changes();")
echo "Updated $UPDATED exposure records."
echo

echo "Verifying update..."
sqlite3 "$DB_FILE" <<EOF
.headers on
.mode column
SELECT
  COUNT(*) as count,
  tracking_ra,
  tracking_dec
FROM exposure
WHERE instrument = 'Nickel'
  AND target_name = '$OBJECT'
GROUP BY tracking_ra, tracking_dec;
EOF

echo
echo "Done! Backup saved to: $BACKUP_FILE"
echo
echo "If something went wrong, restore with:"
echo "  cp $BACKUP_FILE $DB_FILE"
