#!/usr/bin/env bash
# Activate the LSST stack and run a command in that environment.
# Usage:
#   ./scripts/with-stack.sh -S /path/to/lsst_stack [--setup-testdata] -- <command> [args...]
#
# Examples:
#   ./scripts/with-stack.sh -S /opt/lsst/software/stack -- pytest -q
#   TESTDATA_NICKEL_DIR=/mnt/testdata_nickel \
#     ./scripts/with-stack.sh -S /opt/lsst/software/stack --setup-testdata -- pytest -q
#
# Notes:
# - We source loadLSST.bash if present (preferred in LSST images). If only loadLSST.zsh
#   exists, we import its environment via a zsh subprocess.
# - We temporarily relax `set -u` around stack activation since some LSST env scripts
#   reference possibly-unset variables (e.g., DYLD_LIBRARY_PATH on Linux).
# - If --setup-testdata is given, we try `setup testdata_nickel` first; if that fails
#   and $TESTDATA_NICKEL_DIR points at a checkout, we declare+setup from there.

set -euo pipefail

STACK_DIR=""
DO_SETUP_TESTDATA=0

print_usage() {
  cat <<USAGE
Usage: $0 -S /path/to/lsst_stack [--setup-testdata] -- <command> [args...]

Options:
  -S, --stack-dir PATH    Path to LSST stack prefix (directory containing loadLSST.bash|zsh).
      --setup-testdata    Also set up testdata_nickel (pre-installed or from \$TESTDATA_NICKEL_DIR).
  -h, --help              Show this help and exit.

Environment:
  TESTDATA_NICKEL_DIR     If set to a local checkout, will be used to declare+setup testdata_nickel
                          (only if --setup-testdata is provided and a pre-installed product is not found).
USAGE
}

# --------- Parse args (stop at -- and pass the rest through) ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -S|--stack-dir)
      [[ $# -lt 2 ]] && { echo "ERROR: $1 requires a path" >&2; exit 2; }
      STACK_DIR="$2"; shift 2;;
    --setup-testdata)
      DO_SETUP_TESTDATA=1; shift;;
    -h|--help)
      print_usage; exit 0;;
    --)
      shift; break;;
    *)
      # First non-option before --: treat as command start for convenience
      break;;
  esac
done

if [[ -z "${STACK_DIR}" ]]; then
  echo "ERROR: must supply -S/--stack-dir pointing at your LSST stack." >&2
  exit 2
fi

if [[ ! -d "${STACK_DIR}" ]]; then
  echo "ERROR: stack dir not found: ${STACK_DIR}" >&2
  exit 2
fi

# Resolve repo root + package path for monorepo layout.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_SCRIPTS_DIR="${SCRIPT_DIR%/utilities}"
# shellcheck source=/dev/null
source "$REPO_SCRIPTS_DIR/utilities/repo_paths.sh"
TESTDATA_NICKEL_DIR="${TESTDATA_NICKEL_DIR:-$REPO_ROOT/packages/testdata}"

# --------- Activate LSST stack (prefer bash variant) ----------
if [[ -f "${STACK_DIR}/loadLSST.bash" ]]; then
  # Temporarily relax nounset for activation scripts
  set +u
  # shellcheck source=/dev/null
  source "${STACK_DIR}/loadLSST.bash"
  set -u
elif [[ -f "${STACK_DIR}/loadLSST.zsh" ]]; then
  # We are in bash, but only zsh entrypoint exists; import env from a zsh subshell.
  if ! command -v zsh >/dev/null 2>&1; then
    echo "ERROR: only loadLSST.zsh found, but 'zsh' is not available." >&2
    exit 2
  fi
  # Capture environment after sourcing loadLSST.zsh in zsh, then export into bash.
  # Relax nounset while importing.
  set +u
  # Use NUL-separated output to reduce parsing issues.
  while IFS= read -r -d '' line; do
    # Skip read-only or funky lines; simple VAR=VALUE pairs only.
    var="${line%%=*}"
    val="${line#*=}"
    # Basic guard: variable names must be alnum/_ and not empty
    if [[ -n "$var" && "$var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      # Export with printf to preserve content; rely on bash to handle the value as-is.
      printf -v "$var" '%s' "$val"
      export "$var"
    fi
  done < <(zsh -c "source '${STACK_DIR}/loadLSST.zsh' >/dev/null 2>&1; env -0")
  set -u
else
  echo "ERROR: loadLSST.bash or loadLSST.zsh not found in: ${STACK_DIR}" >&2
  exit 2
fi

# --------- Setup core products and this working copy ----------
set +u
# Ensure base stack is ready
setup lsst_distrib

# Declare + setup obs_nickel from the current working tree
eups declare -r "$OBS_NICKEL" obs_nickel -t current 2>/dev/null || true
setup obs_nickel

# Declare + setup obs_nickel_data (curated calibrations)
OBS_NICKEL_DATA_DIR="${REPO_ROOT}/packages/obs_nickel_data"
if [[ -d "$OBS_NICKEL_DATA_DIR" ]]; then
  eups declare -r "$OBS_NICKEL_DATA_DIR" obs_nickel_data -t current 2>/dev/null || true
  setup obs_nickel_data
fi

# Ensure workspace packages are available in PYTHONPATH
# This allows tests to import obs_nickel_data_tools, etc.
WORKSPACE_ROOT="$REPO_ROOT"
for pkg_dir in "${WORKSPACE_ROOT}"/packages/*/src; do
  if [[ -d "$pkg_dir" ]]; then
    export PYTHONPATH="${pkg_dir}:${PYTHONPATH:-}"
  fi
done

set -u

# --------- Optional: setup testdata_nickel ----------
if (( DO_SETUP_TESTDATA == 1 )); then
  echo "[with-stack] Ensuring testdata_nickel..." >&2
  if setup testdata_nickel >/dev/null 2>&1; then
    echo "[with-stack] testdata_nickel set up (pre-installed)." >&2
  elif [[ -n "${TESTDATA_NICKEL_DIR:-}" && -d "${TESTDATA_NICKEL_DIR}" ]]; then
    echo "[with-stack] Declaring testdata_nickel from TESTDATA_NICKEL_DIR: ${TESTDATA_NICKEL_DIR}" >&2
    eups declare -r "${TESTDATA_NICKEL_DIR}" testdata_nickel -t current || true
    if setup testdata_nickel >/dev/null 2>&1; then
      echo "[with-stack] testdata_nickel set up from TESTDATA_NICKEL_DIR." >&2
    else
      echo "[with-stack][WARN] Could not set up testdata_nickel even after declare." >&2
    fi
  else
    echo "[with-stack] testdata_nickel not found; continuing without it." >&2
  fi
fi

# --------- Execute the requested command ----------
if [[ $# -eq 0 ]]; then
  echo "[with-stack] No command provided. Environment is active; printing a brief status." >&2
  set +e
  eups list lsst_distrib || true
  exit 0
fi

exec "$@"
