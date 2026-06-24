#!/usr/bin/env bash
# Resolve the monorepo root (REPO_ROOT) for sourcing scripts.

if [[ -z "${REPO_ROOT:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

export REPO_ROOT
