#!/usr/bin/env python3
"""Logging-visibility tests for degraded modes (audit F-027).

- pipeline.find_bad_coord_exposures distinguishes a crashed in-stack query
  (None -> ERROR + []) from a genuinely empty result ([] -> quiet []).
- stack.run_butler_python surfaces subprocess failures at WARNING with stderr,
  while still returning None for callers.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace


def _coord_config(tmp_path: Path) -> SimpleNamespace:
    profile = SimpleNamespace(night_to_dayobs_offset_days=1)
    return SimpleNamespace(repo=tmp_path, profile=profile)


# --------------------------------------------------------------------------- #
# F-027(c): coordinate validation None (crash) -> ERROR + [] ; [] stays quiet
# --------------------------------------------------------------------------- #
def test_find_bad_coord_none_logs_error_and_returns_empty(
    tmp_path, monkeypatch, caplog
):
    from stips.core import pipeline, stack

    monkeypatch.setattr(stack, "run_butler_python_json", lambda *a, **k: None)

    caplog.set_level(logging.ERROR, logger=pipeline.log.name)
    result = pipeline.find_bad_coord_exposures(
        _coord_config(tmp_path),
        "20230519",
        210.910750,
        54.311694,
        instrument_name="Nickel",
    )

    assert result == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "expected an ERROR when coordinate validation cannot run"
    assert "WITHOUT bad-coordinate exclusion" in errors[0].getMessage()


def test_find_bad_coord_empty_is_quiet(tmp_path, monkeypatch, caplog):
    from stips.core import pipeline, stack

    monkeypatch.setattr(stack, "run_butler_python_json", lambda *a, **k: [])

    caplog.set_level(logging.WARNING, logger=pipeline.log.name)
    result = pipeline.find_bad_coord_exposures(
        _coord_config(tmp_path),
        "20230519",
        210.910750,
        54.311694,
        instrument_name="Nickel",
    )

    assert result == []
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# --------------------------------------------------------------------------- #
# F-027(b): run_butler_python surfaces subprocess failures at WARNING w/ stderr
# --------------------------------------------------------------------------- #
def test_run_butler_python_warns_with_stderr(tmp_path, monkeypatch, caplog):
    from stips.core import stack

    def boom(cmd, cfg, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=2, cmd=cmd, stderr="Traceback: boom-marker-xyz"
        )

    monkeypatch.setattr(stack, "run_with_stack", boom)

    config = SimpleNamespace(repo=tmp_path)
    caplog.set_level(logging.WARNING, logger=stack._log.name)

    out = stack.run_butler_python("print('hi')", config)

    assert out is None  # callers depend on None; logging is the only change
    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("boom-marker-xyz" in m for m in msgs), "stderr should be logged"
