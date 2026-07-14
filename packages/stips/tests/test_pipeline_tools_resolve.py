"""Fail-loud instrument/prefix resolution for standalone pipeline_tools CLIs.

F-043: these tools used to return "Nickel" when the profile was unavailable,
silently masquerading as Nickel for any fork with a broken INSTRUMENT_DIR. The
shared helpers now fail loud (SystemExit) instead, unless an explicit
--instrument flag supplies the value.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.pipeline_tools import _profile_resolve  # noqa: E402


def test_resolve_instrument_name_uses_flag(monkeypatch):
    """An explicit --instrument value wins and needs no profile."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    assert _profile_resolve.resolve_instrument_name("CTIO1m") == "CTIO1m"


def test_resolve_instrument_name_fails_loud_without_profile(monkeypatch):
    """No flag and no loadable profile → SystemExit, not a "Nickel" fallback."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        _profile_resolve.resolve_instrument_name(None)
    assert "INSTRUMENT_DIR" in str(exc.value)


def test_resolve_collection_prefix_falls_back_to_flag(monkeypatch):
    """With no profile but an explicit instrument, use it (prefix == name)."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    assert _profile_resolve.resolve_collection_prefix("CTIO1m") == "CTIO1m"


def test_resolve_collection_prefix_fails_loud_without_profile_or_flag(monkeypatch):
    """No profile and no instrument → SystemExit, not a "Nickel" fallback."""
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        _profile_resolve.resolve_collection_prefix(None)
    assert "INSTRUMENT_DIR" in str(exc.value)
