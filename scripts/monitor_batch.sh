#!/usr/bin/env bash
# monitor_batch.sh — Monitor progress of batch_process_nights.sh
#
# Usage:
#   ./monitor_batch.sh [log_file]
#
# If no log file specified, monitors the most recent batch log

set -euo pipefail

LOG_DIR="${OBS_NICKEL:-$(dirname "$0")/..}/logs/batch"

# Find log file
if [[ $# -eq 1 ]]; then
  LOG_FILE="$1"
elif [[ $# -eq 0 ]]; then
  # Find most recent batch summary
  LOG_FILE=$(ls -t "$LOG_DIR"/batch_*_summary.txt 2>/dev/null | head -1 || echo "")
  if [[ -z "$LOG_FILE" ]]; then
    echo "ERROR: No batch logs found in $LOG_DIR"
    echo "Usage: $0 [log_file]"
    exit 1
  fi
  echo "Monitoring most recent batch: $LOG_FILE"
  echo ""
else
  echo "Usage: $0 [log_file]"
  exit 1
fi

if [[ ! -f "$LOG_FILE" ]]; then
  echo "ERROR: Log file not found: $LOG_FILE"
  exit 1
fi

# Function to display status with colors
display_status() {
  local line="$1"

  # Color codes
  local GREEN='\033[0;32m'
  local RED='\033[0;31m'
  local YELLOW='\033[0;33m'
  local BLUE='\033[0;34m'
  local NC='\033[0m' # No Color

  if [[ "$line" =~ SUCCESS ]]; then
    echo -e "${GREEN}$line${NC}"
  elif [[ "$line" =~ FAILED ]]; then
    echo -e "${RED}$line${NC}"
  elif [[ "$line" =~ SKIPPED ]]; then
    echo -e "${YELLOW}$line${NC}"
  elif [[ "$line" =~ STARTED ]]; then
    echo -e "${BLUE}$line${NC}"
  else
    echo "$line"
  fi
}

# Watch mode or single display
if [[ "${1:-}" == "--watch" ]] || [[ "${1:-}" == "-w" ]]; then
  # Continuous monitoring
  echo "=== Watching $LOG_FILE (Ctrl+C to exit) ==="
  echo ""

  # Follow the file
  tail -f "$LOG_FILE" | while IFS= read -r line; do
    display_status "$line"
  done
else
  # Single display
  clear
  echo "=== Batch Processing Status ==="
  echo ""

  # Display summary
  while IFS= read -r line; do
    display_status "$line"
  done < "$LOG_FILE"

  echo ""
  echo "=== End of Log ==="
  echo ""
  echo "Commands:"
  echo "  Monitor live: $0 --watch"
  echo "  Full log: less $LOG_DIR/batch_*.log"
  echo "  Tail live: tail -f $LOG_DIR/batch_*.log"
fi
