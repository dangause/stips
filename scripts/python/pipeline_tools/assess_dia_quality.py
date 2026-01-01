#!/usr/bin/env python
# ruff: noqa: E402
"""Compatibility wrapper; real implementation lives in obs_nickel_archive_tools."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_SRC = ROOT / "packages" / "archive_tools" / "src"
if ARCHIVE_SRC.exists():
    sys.path.insert(0, str(ARCHIVE_SRC))

from obs_nickel_archive_tools.pipeline_tools.assess_dia_quality import main

if __name__ == "__main__":
    raise SystemExit(main())
