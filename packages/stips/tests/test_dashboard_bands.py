"""Dashboard band resolution fails safe, never fabricating Nickel r/i (F-043).

When a run's log lacks a ``Bands: [...]`` line and no instrument profile is
loadable, the night grid must show an explicit unknown column rather than
silently pretending the run processed r/i.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.dashboard.collector import (  # noqa: E402
    UNKNOWN_BANDS,
    RunInfo,
    _profile_bands,
)


def test_display_bands_uses_parsed_run_bands():
    """A run's parsed bands win over any fallback."""
    info = RunInfo(run_id="run1", bands=["r", "i"])
    assert info.display_bands == ["r", "i"]


def test_display_bands_unknown_without_profile(monkeypatch):
    """No parsed bands and no profile → explicit unknown, not r/i."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    info = RunInfo(run_id="run1")
    assert info.display_bands == UNKNOWN_BANDS
    assert info.display_bands != ["r", "i"]


def test_profile_bands_empty_without_profile(monkeypatch):
    """_profile_bands returns [] (not a Nickel default) when no profile loads."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    assert _profile_bands() == []


def test_create_app_requires_instrument_name():
    """create_app has no default instrument_name (would masquerade as Nickel)."""
    import inspect

    pytest.importorskip("fastapi")
    import stips.dashboard.app as app_mod

    sig = inspect.signature(app_mod.create_app)
    param = sig.parameters["instrument_name"]
    assert param.default is inspect.Parameter.empty
