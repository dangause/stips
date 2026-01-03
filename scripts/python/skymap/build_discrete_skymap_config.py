#!/usr/bin/env python
# ruff: noqa: E402
"""Compatibility wrapper; real implementation lives in obs_nickel_data_tools."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_TOOLS_SRC = ROOT / "packages" / "data_tools" / "src"
if DATA_TOOLS_SRC.exists():
    sys.path.insert(0, str(DATA_TOOLS_SRC))

from obs_nickel_data_tools.skymap.build_discrete_skymap_config import main

if __name__ == "__main__":
    raise SystemExit(main())
