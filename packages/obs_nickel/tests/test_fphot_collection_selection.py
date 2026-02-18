#!/usr/bin/env python3
"""Unit tests for forced-phot diff collection selection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def fphot_module():
    """Import fphot module from data_tools source tree."""
    import sys

    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[2] / "data_tools/src"),
    )
    from obs_nickel_data_tools.core import fphot

    return fphot


def _collections_stdout(*collections: str) -> str:
    lines = ["Name Type", "---- ----"]
    lines.extend(f"{c} RUN" for c in collections)
    return "\n".join(lines) + "\n"


def _data_ids_stdout(has_rows: bool) -> str:
    if not has_rows:
        return "No results. Try --help for more information.\n"
    return "\n".join(
        [
            "instrument  visit   band day_obs  physical_filter",
            "---------- -------- ---- -------- ---------------",
            "    Nickel 85628092    r 20230520               R",
        ]
    )


def test_select_diff_collection_prefers_matching_band(fphot_module, monkeypatch):
    repo = "/fake/repo"
    night = "20230519"
    r_run = f"Nickel/runs/{night}/diff/20260218T175707Z/run"
    i_run = f"Nickel/runs/{night}/diff/20260218T175815Z/run"

    def fake_run_butler(args, *_args, **_kwargs):
        cmd = args[0]
        if cmd == "query-collections":
            return SimpleNamespace(
                returncode=0,
                stdout=_collections_stdout(r_run, i_run),
                stderr="",
            )
        if cmd == "query-data-ids":
            coll = args[args.index("--collections") + 1]
            where = args[args.index("--where") + 1]
            has_rows = (coll == r_run and "band='r'" in where) or (
                coll == i_run and "band='i'" in where
            )
            return SimpleNamespace(
                returncode=0,
                stdout=_data_ids_stdout(has_rows),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(fphot_module, "run_butler", fake_run_butler)

    selected, candidates = fphot_module._select_diff_collection(
        repo, night, config=object(), band="r", log_file=None
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

    def fake_run_butler(args, *_args, **_kwargs):
        cmd = args[0]
        if cmd == "query-collections":
            return SimpleNamespace(
                returncode=0,
                stdout=_collections_stdout(r_run, i_run),
                stderr="",
            )
        if cmd == "query-data-ids":
            # Both runs have data when no band constraint is applied.
            return SimpleNamespace(
                returncode=0,
                stdout=_data_ids_stdout(True),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {args}")

    monkeypatch.setattr(fphot_module, "run_butler", fake_run_butler)

    selected, candidates = fphot_module._select_diff_collection(
        repo, night, config=object(), band=None, log_file=None
    )
    assert candidates == [i_run, r_run]
    assert selected == i_run
