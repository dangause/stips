#!/usr/bin/env python3
"""Unit tests for forced-phot diff collection selection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def fphot_module():
    """Import fphot module from the stips source tree."""
    import sys

    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[1] / "src"),
    )
    from stips.core import fphot

    return fphot


def _nickel_config() -> SimpleNamespace:
    """Minimal config stub exposing a Nickel instrument profile."""
    profile = SimpleNamespace(
        name="Nickel",
        collection_prefix="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
        instrument_class="lsst.obs.stips.active.Instrument",
        night_to_dayobs_offset_days=1,
    )
    return SimpleNamespace(require_profile=lambda: profile)


def _collections_stdout(*collections: str) -> str:
    lines = ["Name Type", "---- ----"]
    lines.extend(f"{c} RUN" for c in collections)
    return "\n".join(lines) + "\n"


def _datasets_stdout(has_rows: bool) -> str:
    """Mimic butler query-datasets output.

    query-datasets returns a table with 'type' as the first column,
    which parse_butler_query_output correctly skips as a header.
    An empty result returns a blank line (no rows after headers).
    """
    if not has_rows:
        return "type run id band instrument physical_filter\n---- --- -- ---- ---------- ---------------\n"
    return "\n".join(
        [
            "type run id band instrument physical_filter",
            "---- --- -- ---- ---------- ---------------",
            "difference_image Nickel/runs/20230519/diff/20260218T175707Z/run 85628092 r Nickel R",
        ]
    )


def test_select_diff_collection_prefers_matching_band(fphot_module, monkeypatch):
    repo = "/fake/repo"
    night = "20230519"
    r_run = f"Nickel/runs/{night}/diff/20260218T175707Z/run"
    i_run = f"Nickel/runs/{night}/diff/20260218T175815Z/run"

    def fake_run_butler_query(args, *_args, **_kwargs):
        cmd = args[0]
        if cmd == "query-collections":
            return SimpleNamespace(
                returncode=0,
                stdout=_collections_stdout(r_run, i_run),
                stderr="",
            )
        if cmd == "query-datasets":
            coll = args[args.index("--collections") + 1]
            where = args[args.index("--where") + 1]
            has_rows = (coll == r_run and "band='r'" in where) or (
                coll == i_run and "band='i'" in where
            )
            return SimpleNamespace(
                returncode=0,
                stdout=_datasets_stdout(has_rows),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(fphot_module, "run_butler_query", fake_run_butler_query)

    selected, candidates = fphot_module._select_diff_collection(
        repo, night, config=_nickel_config(), band="r"
    )
    assert candidates == [i_run, r_run]
    assert selected == r_run


def test_select_diff_collection_uses_latest_when_band_unspecified(
    fphot_module, monkeypatch
):
    repo = "/fake/repo"
    night = "20230519"
    r_run = f"Nickel/runs/{night}/diff/20260218T175707Z/run"
    i_run = f"Nickel/runs/{night}/diff/20260218T175815Z/run"

    def fake_run_butler_query(args, *_args, **_kwargs):
        cmd = args[0]
        if cmd == "query-collections":
            return SimpleNamespace(
                returncode=0,
                stdout=_collections_stdout(r_run, i_run),
                stderr="",
            )
        if cmd == "query-datasets":
            # Both runs have data when no band constraint is applied.
            return SimpleNamespace(
                returncode=0,
                stdout=_datasets_stdout(True),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(fphot_module, "run_butler_query", fake_run_butler_query)

    selected, candidates = fphot_module._select_diff_collection(
        repo, night, config=_nickel_config(), band=None
    )
    assert candidates == [i_run, r_run]
    assert selected == i_run
