#!/usr/bin/env bash
# Resolve repo root and obs_nickel package paths for the monorepo layout.

if [[ -z "${REPO_ROOT:-}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

if [[ -n "${OBS_NICKEL:-}" ]]; then
  if [[ -d "${OBS_NICKEL}/packages/obs_nickel" && ! -d "${OBS_NICKEL}/pipelines" ]]; then
    REPO_ROOT="${OBS_NICKEL}"
    OBS_NICKEL="${REPO_ROOT}/packages/obs_nickel"
  fi
fi

if [[ -z "${OBS_NICKEL:-}" ]]; then
  OBS_NICKEL="${REPO_ROOT}/packages/obs_nickel"
elif [[ ! -d "${OBS_NICKEL}/pipelines" && -d "${REPO_ROOT}/packages/obs_nickel" ]]; then
  OBS_NICKEL="${REPO_ROOT}/packages/obs_nickel"
fi

export REPO_ROOT OBS_NICKEL
