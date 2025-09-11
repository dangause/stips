#!/usr/bin/env bash
# Run a command inside an LSST stack environment.
# Usage:
#   ./scripts/with-stack.sh -S /path/to/stack [--setup-testdata] -- <cmd ...>

set -euo pipefail

STACK_DIR=""
SETUP_TESTDATA=0

# --- helpers ---
_suppress_nounset_begin() {
  # Return 0/1 in global _HAD_U to indicate whether nounset was active
  if [[ -o nounset ]]; then
    set +u
    _HAD_U=1
  else
    _HAD_U=0
  fi
}
_suppress_nounset_end() {
  if [[ "${_HAD_U:-0}" -eq 1 ]]; then
    set -u
  fi
}

# --- parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -S|--stack-dir) STACK_DIR="$2"; shift 2 ;;
    --setup-testdata) SETUP_TESTDATA=1; shift ;;
    --) shift; break ;;
    *) echo "with-stack.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "${STACK_DIR}" ]]; then
  echo "with-stack.sh: ERROR: pass -S / --stack-dir" >&2
  exit 2
fi

# --- source LSST env (disable nounset while activating stack) ---
_suppress_nounset_begin
if [[ -f "${STACK_DIR}/loadLSST.bash" ]]; then
  # shellcheck disable=SC1090
  source "${STACK_DIR}/loadLSST.bash"
elif [[ -f "${STACK_DIR}/loadLSST.zsh" ]]; then
  # import zsh-sourced env into this bash
  eval "$(
    zsh -lc "source '${STACK_DIR}/loadLSST.zsh'; python3 - <<'PY'
import os
for k, v in os.environ.items():
    if k in ('_', 'SHLVL'): continue
    v = v.replace(\"'\", \"'\\\\''\")
    print(f\"export {k}='{v}'\")
PY"
  )"
else
  _suppress_nounset_end
  echo "with-stack.sh: ERROR: loadLSST.[bash|zsh] not found in ${STACK_DIR}" >&2
  exit 2
fi
_suppress_nounset_end

# --- setup base products (also suppress nounset during eups setup) ---
_suppress_nounset_begin
setup lsst_distrib || true
_suppress_nounset_end

# Declare + setup obs_nickel from current checkout so Python can import it
_suppress_nounset_begin
eups declare -r "$(pwd)" obs_nickel -t current 2>/dev/null || true
setup obs_nickel
_suppress_nounset_end

# --- optional: testdata_nickel ---
if [[ "${SETUP_TESTDATA}" -eq 1 ]]; then
  _suppress_nounset_begin
  if setup testdata_nickel >/dev/null 2>&1; then
    echo "[with-stack] testdata_nickel set up (pre-installed)."
  elif [[ -n "${TESTDATA_NICKEL_DIR:-}" && -d "${TESTDATA_NICKEL_DIR}" ]]; then
    echo "[with-stack] Declaring testdata_nickel from TESTDATA_NICKEL_DIR: ${TESTDATA_NICKEL_DIR}"
    eups declare -r "${TESTDATA_NICKEL_DIR}" testdata_nickel -t current || true
    if setup testdata_nickel >/dev/null 2>&1; then
      echo "[with-stack] testdata_nickel set up from TESTDATA_NICKEL_DIR."
    else
      echo "[with-stack][WARN] Could not set up testdata_nickel after declare."
    fi
  else
    echo "[with-stack] testdata_nickel not found; continuing without it."
  fi
  _suppress_nounset_end
fi

# --- run command ---
if [[ $# -eq 0 ]]; then
  echo "with-stack.sh: nothing to run (missing -- <cmd ...>)" >&2
  exit 2
fi

exec "$@"
