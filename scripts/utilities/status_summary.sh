#!/usr/bin/env bash
#
# status_summary.sh — quick view of recent pipeline logs (SUCCESS/ERROR markers)
# Usage: ./scripts/utilities/status_summary.sh [log_dir] [count]
#
# By default scans ./logs and shows the latest 20 log files matching common
# pipeline patterns (cp_*, template_*, diff_*, dia_*).

set -euo pipefail

LOG_DIR="${1:-./logs}"
COUNT="${2:-20}"

shopt -s nullglob
LOGS=($(ls -t "$LOG_DIR"/{cp_*,template_*,diff_*,dia_*}.log 2>/dev/null | head -n "$COUNT"))

if [[ ${#LOGS[@]} -eq 0 ]]; then
  echo "No logs found in $LOG_DIR"
  exit 0
fi

echo "Recent logs in $LOG_DIR (showing up to $COUNT):"
echo ""
for log in "${LOGS[@]}"; do
  base=$(basename "$log")
  status=$(grep -E "SUCCESS|ERROR" "$log" | tail -1 || true)
  [[ -z "$status" ]] && status="(no SUCCESS/ERROR markers found)"
  echo "$base : $status"
done

echo ""
echo "Tip: pass a different log dir or count, e.g.:"
echo "  ./scripts/utilities/status_summary.sh ./logs 50"
