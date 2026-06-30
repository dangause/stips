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


def test_select_diff_collection_prefers_matching_band(fphot_module, monkeypatch):
    repo = "/fake/repo"
    night = "20230519"
    r_run = f"Nickel/runs/{night}/diff/20260218T175707Z/run"
    i_run = f"Nickel/runs/{night}/diff/20260218T175815Z/run"

    def fake_list_collections(config, pattern, *, prefix=None):
        return [r_run, i_run]

    def fake_has_datasets(config, dataset_type, collection, *, where=""):
        # difference_image present only for the matching band per collection
        return (collection == r_run and "band='r'" in where) or (
            collection == i_run and "band='i'" in where
        )

    monkeypatch.setattr(
        fphot_module.butler_query, "list_collections", fake_list_collections
    )
    monkeypatch.setattr(fphot_module.butler_query, "has_datasets", fake_has_datasets)

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

    def fake_list_collections(config, pattern, *, prefix=None):
        return [r_run, i_run]

    def fake_has_datasets(config, dataset_type, collection, *, where=""):
        # Both runs have data when no band constraint is applied.
        return True

    monkeypatch.setattr(
        fphot_module.butler_query, "list_collections", fake_list_collections
    )
    monkeypatch.setattr(fphot_module.butler_query, "has_datasets", fake_has_datasets)

    selected, candidates = fphot_module._select_diff_collection(
        repo, night, config=_nickel_config(), band=None
    )
    assert candidates == [i_run, r_run]
    assert selected == i_run
