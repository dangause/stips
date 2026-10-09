#!/usr/bin/env bash
# install_stack_version.sh — install a specific LSST stack release without touching your current env.
#
# Usage:
#   ./scripts/utilities/install_stack_version.sh --release v30_0_3 [--prefix ~/lsst_stacks] [--lsstinstall /path/to/lsstinstall] [--python 3.12] [--install-distrib]
#
# Notes:
# - This is a thin convenience wrapper around `lsstinstall`, following Rubin's
#   documented flow: create <prefix>/<release>, run `lsstinstall -T <release>`
#   from inside it (lsstinstall installs into the CURRENT directory), then
#   optionally `source loadLSST.sh && eups distrib install -t <release> lsst_distrib`.
# - It does not modify your existing stack: it installs into a separate
#   directory with its own conda, so you can point STACK_DIR (in your config
#   YAML's env: block) at the new version when you want to use it.
# - You need network access and `lsstinstall` available. If missing, download
#   it from https://ls.st/lsstinstall

# set -euo pipefail

RELEASE=""
# Default install root: LSST_STACKS_ROOT > ~/lsst_stacks. Never STACK_DIR: that
# would nest the new stack inside the existing one.
PREFIX="${LSST_STACKS_ROOT:-$HOME/lsst_stacks}"
LSSTINSTALL_BIN="${LSSTINSTALL_BIN:-}"
PYVER=""  # optional, passed to lsstinstall (-y)
INSTALL_DISTRIB=false

usage() {
  cat <<USAGE
Usage: $0 --release <tag> [--prefix DIR] [--lsstinstall PATH] [--python X.Y] [--install-distrib]

Installs into <prefix>/<tag>. --python is passed to lsstinstall -y (experimental
upstream; it disables binary packages). --install-distrib also installs
lsst_distrib with eups.

Examples:
  $0 --release v30_0_3
  $0 --release v30_0_3 --prefix /opt/lsst_stacks --install-distrib

Env vars:
  LSST_STACKS_ROOT   Default install root (fallback: ~/lsst_stacks)
  LSSTINSTALL_BIN    Path to lsstinstall if not on PATH
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --release) RELEASE="${2:-}"; shift 2;;
    --prefix) PREFIX="${2:-}"; shift 2;;
    --lsstinstall) LSSTINSTALL_BIN="${2:-}"; shift 2;;
    --python) PYVER="${2:-}"; shift 2;;
    --install-distrib) INSTALL_DISTRIB=true; shift 1;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

if [[ -z "$RELEASE" ]]; then
  echo "ERROR: --release is required (e.g., v30_0_3, w_2025_32, w_latest)" >&2
  usage
  exit 2
fi

mkdir -p "$PREFIX"

if [[ -z "$LSSTINSTALL_BIN" ]]; then
  if command -v lsstinstall >/dev/null 2>&1; then
    LSSTINSTALL_BIN="$(command -v lsstinstall)"
  elif [[ -x "$PREFIX/lsstinstall" ]]; then
    LSSTINSTALL_BIN="$PREFIX/lsstinstall"
  else
    echo "ERROR: lsstinstall not found. Download it (network required):" >&2
    echo "  curl -sSfL https://ls.st/lsstinstall -o $PREFIX/lsstinstall" >&2
    echo "  chmod +x $PREFIX/lsstinstall" >&2
    exit 2
  fi
fi
if [[ ! -x "$LSSTINSTALL_BIN" ]]; then
  echo "ERROR: $LSSTINSTALL_BIN is not executable (chmod u+x it)" >&2
  exit 2
fi

# lsstinstall installs into the current directory, so it runs from inside the
# target; resolve both paths to absolute ones first.
TARGET="${PREFIX}/${RELEASE}"
mkdir -p "$TARGET" || exit 2
TARGET="$(cd "$TARGET" && pwd)"
LSSTINSTALL_BIN="$(cd "$(dirname "$LSSTINSTALL_BIN")" && pwd)/$(basename "$LSSTINSTALL_BIN")"

# lsstinstall takes the EUPS tag via -T and rejects positional arguments. -P
# makes it install a fresh conda in the target instead of reusing a conda that
# is active in the calling shell (which would put the release into that stack).
cmd=("$LSSTINSTALL_BIN" "-P" "-T" "$RELEASE")
if [[ -n "$PYVER" ]]; then
  cmd+=("-y" "$PYVER")
fi

if [[ -f "$TARGET/loadLSST.sh" ]]; then
  echo "[skip] lsstinstall already ran in $TARGET (loadLSST.sh present)"
else
  echo "[info] Installing stack release '$RELEASE' into $TARGET"
  echo "[info] Command (in $TARGET): ${cmd[*]}"
  if ! (cd "$TARGET" && "${cmd[@]}"); then
    echo "ERROR: lsstinstall failed for $RELEASE in $TARGET" >&2
    exit 1
  fi
fi

if [[ "$INSTALL_DISTRIB" == "true" ]]; then
  echo "[info] Installing lsst_distrib with tag $RELEASE"
  if [[ ! -f "$TARGET/loadLSST.sh" ]]; then
    echo "ERROR: loadLSST.sh not found at $TARGET; cannot install lsst_distrib" >&2
    exit 2
  fi
  # Activate the new stack's own env: an LSST_CONDA_ENV_NAME inherited from a
  # stack loaded in the calling shell names an env the new conda does not have.
  unset LSST_CONDA_ENV_NAME
  # shellcheck source=/dev/null
  if ! source "$TARGET/loadLSST.sh"; then
    echo "ERROR: could not activate the new stack via $TARGET/loadLSST.sh" >&2
    exit 2
  fi
  if ! command -v eups >/dev/null 2>&1; then
    echo "ERROR: eups not available after sourcing $TARGET/loadLSST.sh" >&2
    exit 2
  fi
  if ! eups distrib install -t "$RELEASE" lsst_distrib; then
    echo "ERROR: eups distrib install failed for tag $RELEASE" >&2
    exit 2
  fi
  echo "[ok] Installed $RELEASE (lsst_distrib) at $TARGET"
else
  cat <<NEXT
[ok] Bootstrapped $RELEASE at $TARGET (conda env + eups; no lsst_distrib yet)

Install the Science Pipelines by rerunning with --install-distrib, or:
  source "$TARGET/loadLSST.sh"
  eups distrib install -t $RELEASE lsst_distrib
NEXT
fi

cat <<DONE

To use it, set STACK_DIR in your config YAML's env: block:
  STACK_DIR: $TARGET
DONE
