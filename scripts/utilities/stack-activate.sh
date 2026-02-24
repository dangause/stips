# Usage:
#   source scripts/stack-activate.sh -S /path/to/lsst_stack
# Optional:
#   source scripts/stack-activate.sh -S /path/to/stack --no-testdata
#
# Effect: activates LSST stack + sets up obs_nickel (+ testdata_nickel by default)
# in the CURRENT shell (required so env persists).


STACK_DIR=""
SETUP_TESTDATA=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -S|--stack-dir) STACK_DIR="$2"; shift 2 ;;
    --no-testdata)  SETUP_TESTDATA=0; shift ;;
    -h|--help)
      echo "source $0 -S /path/to/lsst_stack [--no-testdata]"
      return 0 ;;
    *) echo "Unknown arg: $1"; return 1 ;;
  esac
done

if [[ -z "${STACK_DIR}" ]]; then
  echo "ERROR: pass -S / --stack-dir"; return 2
fi

# Resolve repo root + package path for monorepo layout.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/repo_paths.sh"
TESTDATA_NICKEL_DIR="${TESTDATA_NICKEL_DIR:-$REPO_ROOT/packages/testdata}"

if [[ -f "${STACK_DIR}/loadLSST.zsh" ]]; then
  nounset_was_on=0; if set -o | grep -q 'nounset *on'; then nounset_was_on=1; set +u; fi
  # shellcheck disable=SC1091
  source "${STACK_DIR}/loadLSST.zsh"
  [[ $nounset_was_on -eq 1 ]] && set -u
elif [[ -f "${STACK_DIR}/loadLSST.bash" ]]; then
  nounset_was_on=0; if set -o | grep -q 'nounset *on'; then nounset_was_on=1; set +u; fi
  # shellcheck disable=SC1091
  source "${STACK_DIR}/loadLSST.bash"
  [[ $nounset_was_on -eq 1 ]] && set -u
else
  echo "ERROR: loadLSST.[zsh|bash] not found in ${STACK_DIR}"
  return 2
fi

setup lsst_distrib

# Declare + setup obs_nickel from this working copy
eups declare -r "$OBS_NICKEL" obs_nickel -t current 2>/dev/null || true
setup obs_nickel

# Declare + setup obs_nickel_data (curated calibrations)
OBS_NICKEL_DATA_DIR="${REPO_ROOT}/packages/obs_nickel_data"
if [ -d "$OBS_NICKEL_DATA_DIR" ]; then
  eups declare -r "$OBS_NICKEL_DATA_DIR" obs_nickel_data -t current 2>/dev/null || true
  setup obs_nickel_data
fi

# ---------- testdata_nickel ----------
# Prefer already-installed product; then optional local declare; otherwise skip.
if [ "${SETUP_TESTDATA:-1}" -eq 1 ]; then
  echo "[stack-activate] Ensuring testdata_nickel is available..."

  if setup testdata_nickel >/dev/null 2>&1; then
    echo "[stack-activate] testdata_nickel set up (pre-installed)."
  elif [ -n "${TESTDATA_NICKEL_DIR:-}" ] && [ -d "$TESTDATA_NICKEL_DIR" ]; then
    echo "[stack-activate] Declaring testdata_nickel from TESTDATA_NICKEL_DIR: $TESTDATA_NICKEL_DIR"
    eups declare -r "$TESTDATA_NICKEL_DIR" testdata_nickel -t current || true
    if setup testdata_nickel >/dev/null 2>&1; then
      echo "[stack-activate] testdata_nickel set up from TESTDATA_NICKEL_DIR."
    else
      echo "[stack-activate][WARN] Could not set up testdata_nickel even after declare."
    fi
  else
    echo "[stack-activate] testdata_nickel not found; skipping. (tests that need it will skip)"
    echo "  Tip: run 'setup testdata_nickel' or set TESTDATA_NICKEL_DIR=/path/to/testdata_nickel and re-source."
  fi
else
  echo "[stack-activate] Skipping testdata_nickel per --no-testdata."
fi


echo "LSST env active. obs_nickel and obs_nickel_data are set up."
