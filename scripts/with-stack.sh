#!/usr/bin/env bash
# Execute a command under the LSST stack + obs_nickel environment.
#
# Usage:
#   scripts/with-stack.sh -S /path/to/lsst_stack -- <command> [args...]
# Optional:
#   scripts/with-stack.sh -S /path/to/stack --setup-testdata -- <command>
#
set -Ee -o pipefail

STACK_DIR=""
SETUP_TESTDATA=0
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    -S|--stack-dir) STACK_DIR="$2"; shift 2 ;;
    --setup-testdata) SETUP_TESTDATA=1; shift ;;
    --) shift; break ;;
    -h|--help)
      cat <<EOF
Usage:
  $0 -S /path/to/lsst_stack [--setup-testdata] -- <command> [args...]

Env:
  TESTDATA_NICKEL_DIR=/abs/path/to/testdata_nickel (optional when --setup-testdata)
EOF
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "${STACK_DIR}" ]] || { echo "ERROR: pass -S / --stack-dir" >&2; exit 2; }
[[ $# -gt 0 ]] || { echo "ERROR: provide a command after '--'." >&2; exit 2; }

# Find loadLSST.* (prefer file matching current shell)
_find_loadlsst() {
  local candidates=()
  if [[ -n "${BASH_VERSION:-}" ]]; then
    candidates+=(
      "$STACK_DIR/loadLSST.bash" "$STACK_DIR/software/stack/loadLSST.bash" "$STACK_DIR/stack/loadLSST.bash"
      "$STACK_DIR/loadLSST.zsh"  "$STACK_DIR/software/stack/loadLSST.zsh"  "$STACK_DIR/stack/loadLSST.zsh"
    )
  elif [[ -n "${ZSH_VERSION:-}" ]]; then
    candidates+=(
      "$STACK_DIR/loadLSST.zsh"  "$STACK_DIR/software/stack/loadLSST.zsh"  "$STACK_DIR/stack/loadLSST.zsh"
      "$STACK_DIR/loadLSST.bash" "$STACK_DIR/software/stack/loadLSST.bash" "$STACK_DIR/stack/loadLSST.bash"
    )
  else
    candidates+=(
      "$STACK_DIR/loadLSST.bash" "$STACK_DIR/loadLSST.zsh"
      "$STACK_DIR/software/stack/loadLSST.bash" "$STACK_DIR/software/stack/loadLSST.zsh"
      "$STACK_DIR/stack/loadLSST.bash" "$STACK_DIR/stack/loadLSST.zsh"
    )
  fi
  for cand in "${candidates[@]}"; do [[ -f "$cand" ]] && { echo "$cand"; return 0; }; done
  local found; found="$(find "$STACK_DIR" -maxdepth 4 -type f -name 'loadLSST.*' 2>/dev/null | head -n1 || true)"
  [[ -n "$found" ]] && { echo "$found"; return 0; }
  return 1
}

LOAD_FILE="$(_find_loadlsst)" || { echo "ERROR: could not find loadLSST.[bash|zsh] under: $STACK_DIR" >&2; exit 2; }

# Temporarily disable nounset while sourcing stack (avoids conda hook 'unbound variable' issues)
nounset_was_on=0
if set -o | grep -q 'nounset *on'; then
  nounset_was_on=1
  set +u
fi

# shellcheck disable=SC1090
source "$LOAD_FILE"

# Restore nounset if it was on
if [[ $nounset_was_on -eq 1 ]]; then
  set -u
fi

setup lsst_distrib

# Ensure this repo is active obs_nickel
eups declare -r "$REPO_ROOT" obs_nickel -t current 2>/dev/null || true
setup obs_nickel

# Optional: testdata
if [[ "$SETUP_TESTDATA" -eq 1 ]]; then
  if setup testdata_nickel >/dev/null 2>&1; then
    echo "[with-stack] testdata_nickel set up (pre-installed)."
  elif [[ -n "${TESTDATA_NICKEL_DIR:-}" && -d "$TESTDATA_NICKEL_DIR" ]]; then
    echo "[with-stack] Declaring testdata_nickel from TESTDATA_NICKEL_DIR: $TESTDATA_NICKEL_DIR"
    eups declare -r "$TESTDATA_NICKEL_DIR" testdata_nickel -t current || true
    if setup testdata_nickel >/dev/null 2>&1; then
      echo "[with-stack] testdata_nickel set up from TESTDATA_NICKEL_DIR."
    else
      echo "[with-stack][WARN] Could not set up testdata_nickel even after declare."
    fi
  else
    echo "[with-stack] testdata_nickel not found; continuing without it."
  fi
fi

# Run the command
exec "$@"
