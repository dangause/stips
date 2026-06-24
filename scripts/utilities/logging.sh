#!/usr/bin/env bash
#
# logging.sh - Centralized logging utilities for LSST pipeline scripts
#
# This provides a consistent nested directory structure for all pipeline logs:
#
# $LOG_ROOT/
#   └── YYYYMMDD_HHMMSS_{run_id}/        # Top-level run directory
#       ├── run_info.txt                  # Run metadata (command, date, config)
#       ├── summary.txt                   # Final summary (success/fail counts)
#       ├── bootstrap/                    # 00_bootstrap_repo.sh logs
#       │   └── bootstrap.log
#       ├── calibs/                       # 10_calibs.sh logs
#       │   └── {night}/
#       │       ├── calibs.log            # Main calibs processing log
#       │       ├── cpBias.log            # Individual task logs
#       │       ├── cpFlat.log
#       │       └── defects.log
#       ├── science/                      # 20_science.sh logs
#       │   └── {night}/
#       │       ├── science.log           # Main science processing log
#       │       ├── processCcd.log        # Single-visit processing
#       │       └── coadds.log            # Coadd processing (if run)
#       ├── templates/                    # 30_coadds.sh logs
#       │   └── {band}/
#       │       └── tract_{tract}/
#       │           └── template.log
#       ├── dia/                          # 40_diff_imaging.sh logs
#       │   └── {night}/
#       │       └── {band}/
#       │           ├── dia.log           # Main DIA log
#       │           ├── quantum.log       # Quantum graph details
#       │           └── results.txt       # Summary stats
#       └── other/                        # Other scripts (PS1 ingest, etc.)
#           └── {script_name}/
#               └── {timestamp}.log
#
# Usage in pipeline scripts:
#   source "$(dirname "$0")/../utilities/logging.sh"
#   setup_logging "calibs" "$NIGHT"
#   log "Processing night $NIGHT..."
#   exec > >(tee -a "$LOG_FILE") 2>&1  # Redirect all output to log
#

# Default log root (can be overridden by setting LOG_ROOT before sourcing)
# Resolve REPO_ROOT.
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/repo_paths.sh"
# Logs go in repo root.
: "${LOG_ROOT:=${REPO_ROOT}/logs}"

# Current run ID (shared across all scripts in a single pipeline execution)
# This can be set externally or auto-generated
: "${RUN_ID:=$(date -u +%Y%m%d_%H%M%S)_$$}"

# Top-level run directory for this execution
RUN_LOG_DIR="$LOG_ROOT/$RUN_ID"

# Helper function to set a custom RUN_ID and update RUN_LOG_DIR
# Call this BEFORE setup_logging() if you want a custom run ID
# Usage: set_run_id "my_custom_run_id"
set_run_id() {
  local new_run_id="$1"
  export RUN_ID="$new_run_id"
  export RUN_LOG_DIR="$LOG_ROOT/$RUN_ID"
}

# Logging functions
log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

log_info() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [INFO] $*"
}

log_warn() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [WARN] $*" >&2
}

log_error() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [ERROR] $*" >&2
}

log_section() {
  echo ""
  echo "========================================"
  echo "  $*"
  echo "========================================"
}

# Setup logging for a specific pipeline stage
# Args:
#   $1: stage name (bootstrap|calibs|science|templates|dia|other)
#   $2: night (YYYYMMDD, optional for bootstrap/other)
#   $3: band (optional, for templates/dia)
#   $4: tract (optional, for templates)
#   $5: script name (optional, for other)
setup_logging() {
  local stage="$1"
  local night="${2:-}"
  local band="${3:-}"
  local tract="${4:-}"
  local script_name="${5:-}"

  # Ensure run directory exists
  mkdir -p "$RUN_LOG_DIR"

  # Create run_info.txt on first setup
  if [[ ! -f "$RUN_LOG_DIR/run_info.txt" ]]; then
    {
      echo "Run ID: $RUN_ID"
      echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "Command: ${0##*/}"
      echo "Working dir: $PWD"
      echo "Repository: ${REPO:-unknown}"
      echo ""
    } > "$RUN_LOG_DIR/run_info.txt"
  fi

  # Build stage-specific directory path
  case "$stage" in
    bootstrap)
      LOG_DIR="$RUN_LOG_DIR/bootstrap"
      LOG_FILE="$LOG_DIR/bootstrap.log"
      ;;
    calibs)
      [[ -z "$night" ]] && { echo "ERROR: night required for calibs logging" >&2; return 1; }
      LOG_DIR="$RUN_LOG_DIR/calibs/$night"
      LOG_FILE="$LOG_DIR/calibs.log"
      ;;
    science)
      [[ -z "$night" ]] && { echo "ERROR: night required for science logging" >&2; return 1; }
      LOG_DIR="$RUN_LOG_DIR/science/$night"
      LOG_FILE="$LOG_DIR/science.log"
      ;;
    templates)
      [[ -z "$band" ]] && { echo "ERROR: band required for templates logging" >&2; return 1; }
      if [[ -n "$tract" ]]; then
        LOG_DIR="$RUN_LOG_DIR/templates/$band/tract_$tract"
      else
        LOG_DIR="$RUN_LOG_DIR/templates/$band"
      fi
      LOG_FILE="$LOG_DIR/template.log"
      ;;
    dia)
      [[ -z "$night" ]] && { echo "ERROR: night required for dia logging" >&2; return 1; }
      if [[ -n "$band" ]]; then
        LOG_DIR="$RUN_LOG_DIR/dia/$night/$band"
      else
        LOG_DIR="$RUN_LOG_DIR/dia/$night"
      fi
      LOG_FILE="$LOG_DIR/dia.log"
      ;;
    other)
      [[ -z "$script_name" ]] && script_name="misc"
      LOG_DIR="$RUN_LOG_DIR/other/$script_name"
      LOG_FILE="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ).log"
      ;;
    *)
      echo "ERROR: Unknown logging stage: $stage" >&2
      return 1
      ;;
  esac

  # Create directory and export variables
  mkdir -p "$LOG_DIR"
  export LOG_DIR
  export LOG_FILE
  export RUN_LOG_DIR

  log_info "Logging to: $LOG_FILE"
}

# Create a task-specific log file within the current LOG_DIR
# Args:
#   $1: task name (e.g., "cpBias", "processCcd", "quantum")
# Returns: path to task log file
get_task_log() {
  local task_name="$1"
  [[ -z "$LOG_DIR" ]] && { echo "ERROR: setup_logging not called" >&2; return 1; }

  local task_log="$LOG_DIR/${task_name}.log"
  echo "$task_log"
}

# Write summary statistics to run directory
# Args:
#   $1: summary text (multiline string)
write_summary() {
  local summary_file="$RUN_LOG_DIR/summary.txt"
  echo "$1" > "$summary_file"
  log_info "Summary written to: $summary_file"
}

# Append to run_info.txt
# Args:
#   $1: info text to append
append_run_info() {
  echo "$1" >> "$RUN_LOG_DIR/run_info.txt"
}

# Print final log location
print_log_summary() {
  echo ""
  echo "========================================"
  echo "  Logs saved to:"
  echo "========================================"
  echo "  Run directory: $RUN_LOG_DIR"
  if [[ -f "$LOG_FILE" ]]; then
    echo "  Main log: $LOG_FILE"
  fi
  if [[ -f "$RUN_LOG_DIR/summary.txt" ]]; then
    echo "  Summary: $RUN_LOG_DIR/summary.txt"
  fi
  echo ""
}

# Export functions for use in subshells
export -f log log_info log_warn log_error log_section
export -f setup_logging get_task_log write_summary append_run_info print_log_summary
