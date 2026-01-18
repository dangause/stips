#!/usr/bin/env bash
#
# monitor_dia_progress.sh - Monitor progress of run_dia_multi_band.sh
#
# Usage:
#   # If output is going to a log file:
#   ./scripts/pipeline/monitor_dia_progress.sh /path/to/logfile.log
#
#   # If monitoring a running process by PID:
#   ./scripts/pipeline/monitor_dia_progress.sh --pid 12345
#
#   # Live monitoring (reads from stdin, use with tee):
#   ./run_dia_multi_band.sh ... 2>&1 | tee dia_run.log
#   # In another terminal:
#   tail -f dia_run.log | ./scripts/pipeline/monitor_dia_progress.sh
#

set -euo pipefail

LOG_FILE="${1:-}"
REFRESH_INTERVAL=2

# ANSI color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

usage() {
  cat <<EOF
Usage: $0 [LOG_FILE]

Monitor the progress of run_dia_multi_band.sh by parsing its log output.

Arguments:
  LOG_FILE    Path to log file (optional, reads from stdin if not provided)

Examples:
  # Monitor log file
  $0 dia_run.log

  # Monitor live output
  tail -f dia_run.log | $0

  # Run with tee for live monitoring
  ./run_dia_multi_band.sh ... 2>&1 | tee dia_run.log
  # In another terminal:
  tail -f dia_run.log | $0
EOF
  exit 1
}

[[ "$LOG_FILE" == "-h" || "$LOG_FILE" == "--help" ]] && usage

parse_log() {
  local input="${1:-/dev/stdin}"

  # Counters
  local total_calibs=0
  local completed_calibs=0
  local failed_calibs=0

  local total_science=0
  local completed_science=0
  local failed_science=0

  local total_templates=0
  local completed_templates=0
  local failed_templates=0

  local total_dia=0
  local completed_dia=0
  local failed_dia=0

  local current_stage=""
  local current_band=""
  local bands_list=""

  # Arrays for failures
  declare -a failed_calibs_nights=()
  declare -a failed_science_nights=()
  declare -a failed_template_bands=()
  declare -a failed_dia_items=()

  # Read log line by line
  while IFS= read -r line; do
    # Detect stages
    if [[ "$line" =~ "Stage 1: Calibs" ]]; then
      current_stage="Calibs"
    elif [[ "$line" =~ "Stage 2: Science" ]]; then
      current_stage="Science"
    elif [[ "$line" =~ "=== Band: "([a-z]+)" ===" ]]; then
      current_band="${BASH_REMATCH[1]}"
      current_stage="Template/DIA for band $current_band"
      [[ -z "$bands_list" ]] && bands_list="$current_band" || bands_list="$bands_list,$current_band"
    fi

    # Calibs
    if [[ "$line" =~ "Running: ./scripts/pipeline/10_calibs.sh --night "([0-9]+) ]]; then
      ((total_calibs++))
      ((completed_calibs++))
    elif [[ "$line" =~ "Calibs failed for night "([0-9]+) ]]; then
      ((failed_calibs++))
      ((completed_calibs--))
      failed_calibs_nights+=("${BASH_REMATCH[1]}")
    fi

    # Science
    if [[ "$line" =~ "Running: ./scripts/pipeline/20_science.sh" ]]; then
      ((total_science++))
      ((completed_science++))
    elif [[ "$line" =~ "Science failed for night "([0-9]+) ]]; then
      ((failed_science++))
      ((completed_science--))
      failed_science_nights+=("${BASH_REMATCH[1]}")
    fi

    # Templates
    if [[ "$line" =~ "Running: ./scripts/pipeline/30_coadds.sh" ]]; then
      ((total_templates++))
      ((completed_templates++))
    elif [[ "$line" =~ "Template build failed for band "([a-z]+) ]]; then
      ((failed_templates++))
      ((completed_templates--))
      failed_template_bands+=("${BASH_REMATCH[1]}")
    fi

    # DIA
    if [[ "$line" =~ "Running: ./scripts/pipeline/40_diff_imaging.sh" ]]; then
      ((total_dia++))
      ((completed_dia++))
    elif [[ "$line" =~ "DIA failed for night "([0-9]+)" band "([a-z]+) ]]; then
      ((failed_dia++))
      ((completed_dia--))
      failed_dia_items+=("${BASH_REMATCH[1]}/${BASH_REMATCH[2]}")
    fi
  done < "$input"

  # Display summary
  clear
  echo -e "${BOLD}=== DIA Multi-Band Pipeline Progress ===${NC}"
  echo -e "Current stage: ${BLUE}${current_stage:-Not started}${NC}"
  [[ -n "$bands_list" ]] && echo -e "Bands:         ${bands_list}"
  echo ""

  echo -e "${BOLD}Stage 1: Calibrations${NC}"
  echo -e "  Total:     $total_calibs"
  echo -e "  ${GREEN}Completed: $completed_calibs${NC}"
  echo -e "  ${RED}Failed:    $failed_calibs${NC}"
  if [[ ${#failed_calibs_nights[@]} -gt 0 ]]; then
    echo -e "    ${RED}Failed nights: ${failed_calibs_nights[*]}${NC}"
  fi
  echo ""

  echo -e "${BOLD}Stage 2: Science Processing${NC}"
  echo -e "  Total:     $total_science"
  echo -e "  ${GREEN}Completed: $completed_science${NC}"
  echo -e "  ${RED}Failed:    $failed_science${NC}"
  if [[ ${#failed_science_nights[@]} -gt 0 ]]; then
    echo -e "    ${RED}Failed nights: ${failed_science_nights[*]}${NC}"
  fi
  echo ""

  echo -e "${BOLD}Stage 3: Template Building${NC}"
  echo -e "  Total:     $total_templates"
  echo -e "  ${GREEN}Completed: $completed_templates${NC}"
  echo -e "  ${RED}Failed:    $failed_templates${NC}"
  if [[ ${#failed_template_bands[@]} -gt 0 ]]; then
    echo -e "    ${RED}Failed bands: ${failed_template_bands[*]}${NC}"
  fi
  echo ""

  echo -e "${BOLD}Stage 4: DIA Processing${NC}"
  echo -e "  Total:     $total_dia"
  echo -e "  ${GREEN}Completed: $completed_dia${NC}"
  echo -e "  ${RED}Failed:    $failed_dia${NC}"
  if [[ ${#failed_dia_items[@]} -gt 0 ]]; then
    echo -e "    ${RED}Failed: ${failed_dia_items[*]}${NC}"
  fi
  echo ""

  # Overall status
  local total_failed=$((failed_calibs + failed_science + failed_templates + failed_dia))
  if [[ $total_failed -gt 0 ]]; then
    echo -e "${RED}${BOLD}Overall: $total_failed failures detected${NC}"
  else
    echo -e "${GREEN}${BOLD}Overall: No failures detected${NC}"
  fi

  echo ""
  echo -e "${BLUE}Last updated: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
}

# Main execution
if [[ -n "$LOG_FILE" ]]; then
  # Monitor log file with periodic refresh
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "ERROR: Log file not found: $LOG_FILE"
    exit 1
  fi

  echo "Monitoring log file: $LOG_FILE"
  echo "Press Ctrl+C to exit"
  echo ""

  while true; do
    parse_log "$LOG_FILE"
    sleep "$REFRESH_INTERVAL"
  done
else
  # Read from stdin (one-shot)
  parse_log
fi
