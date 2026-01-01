#!/usr/bin/env bash
# install_stack_version.sh — install a specific LSST stack release without touching your current env.
#
# Usage:
#   ./scripts/utilities/install_stack_version.sh --release w_2025_10 [--prefix ~/lsst_stacks] [--lsstinstall /path/to/lsstinstall] [--python 3.12]
#
# Notes:
# - This is a thin convenience wrapper around `lsstinstall`. It does not modify
#   your existing stack; it installs into a separate prefix so you can point
#   `.env:STACK_DIR` at the new version when you want to use it.
# - You need network access and `lsstinstall` available. If missing, download
#   it from https://raw.githubusercontent.com/lsst/lsst/main/scripts/lsstinstall/lsstinstall

set -euo pipefail

RELEASE=""
PREFIX="${LSST_STACKS_ROOT:-$HOME/lsst_stacks}"
LSSTINSTALL_BIN="${LSSTINSTALL_BIN:-}"
PYVER=""  # optional, passed to lsstinstall (-P)

usage() {
  cat <<USAGE
Usage: $0 --release <tag> [--prefix DIR] [--lsstinstall PATH] [--python X.Y]

Examples:
  $0 --release w_2025_10
  $0 --release r_28_0_0 --prefix /opt/lsst_stacks

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
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

if [[ -z "$RELEASE" ]]; then
  echo "ERROR: --release is required (e.g., w_2025_10, r_28_0_0, d_latest)" >&2
  usage
  exit 2
fi

mkdir -p "$PREFIX"
TARGET="${PREFIX}/${RELEASE}"

if [[ -d "$TARGET" && -f "$TARGET/loadLSST.zsh" ]]; then
  echo "[skip] Stack already present at $TARGET"
  exit 0
fi

if [[ -z "$LSSTINSTALL_BIN" ]]; then
  if command -v lsstinstall >/dev/null 2>&1; then
    LSSTINSTALL_BIN="$(command -v lsstinstall)"
  elif [[ -x "$PREFIX/lsstinstall" ]]; then
    LSSTINSTALL_BIN="$PREFIX/lsstinstall"
  else
    echo "ERROR: lsstinstall not found. Download it (network required):" >&2
    echo "  curl -sSfL https://raw.githubusercontent.com/lsst/lsst/main/scripts/lsstinstall/lsstinstall -o $PREFIX/lsstinstall" >&2
    echo "  chmod +x $PREFIX/lsstinstall" >&2
    exit 2
  fi
fi

cmd=("$LSSTINSTALL_BIN" "-T" "$TARGET")
if [[ -n "$PYVER" ]]; then
  cmd+=("-P" "$PYVER")
fi
cmd+=("$RELEASE")

echo "[info] Installing stack release '$RELEASE' into $TARGET"
echo "[info] Command: ${cmd[*]}"
"${cmd[@]}"

cat <<DONE
[ok] Installed $RELEASE at $TARGET

To use it, update .env:
  STACK_DIR=$TARGET

Then rerun your pipeline commands (they source .env and load the stack).
DONE
