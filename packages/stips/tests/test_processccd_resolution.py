#!/usr/bin/env python3
"""Unit tests for the shared processCcd / raw collection resolvers.

Covers the single source of truth for the "prefer the CHAINED parent over the
individual ``/run`` and ``/run_fb*`` RUNs" policy used by DIA, coadd, and forced
photometry (F-037), plus ``fphot`` ``image_type`` validation (F-049).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def pipeline_module():
    """Import the pipeline module from the stips source tree."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from stips.core import pipeline

    return pipeline


@pytest.fixture
def fphot_module():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from stips.core import fphot

    return fphot


def _nickel_config() -> SimpleNamespace:
    profile = SimpleNamespace(name="Nickel", collection_prefix="Nickel")
    return SimpleNamespace(require_profile=lambda: profile)


def _fake_list(names):
    def _inner(config, pattern, *, prefix=None):
        return list(names)

    return _inner


# --------------------------------------------------------------------------- #
# latest_raw_run
# --------------------------------------------------------------------------- #
def test_latest_raw_run_picks_newest(pipeline_module, monkeypatch):
    # list_collections returns sorted (ascending) names; newest is last.
    names = [
        "Nickel/raw/20230519/20230101T000000Z",
        "Nickel/raw/20230519/20240202T000000Z",  # newest (post re-ingest)
    ]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    assert (
        pipeline_module.latest_raw_run(_nickel_config(), "20230519")
        == "Nickel/raw/20230519/20240202T000000Z"
    )


def test_latest_raw_run_none_when_empty(pipeline_module, monkeypatch):
    monkeypatch.setattr(
        pipeline_module.butler_query,
        "list_collections",
        lambda config, pattern, *, prefix=None: [],
    )
    assert pipeline_module.latest_raw_run(_nickel_config(), "20230519") is None


def test_latest_raw_run_none_on_query_failure(pipeline_module, monkeypatch):
    # list_collections returns None when the in-stack query fails.
    monkeypatch.setattr(
        pipeline_module.butler_query,
        "list_collections",
        lambda config, pattern, *, prefix=None: None,
    )
    assert pipeline_module.latest_raw_run(_nickel_config(), "20230519") is None


# --------------------------------------------------------------------------- #
# resolve_processccd_collections — parent preference & ordering
# --------------------------------------------------------------------------- #
def test_resolver_prefers_parent_over_run_and_run_fb(pipeline_module, monkeypatch):
    base = "Nickel/runs/20230519/processCcd/ts1"
    names = [base, f"{base}/run", f"{base}/run_fb1", f"{base}/run_fb2"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    got = pipeline_module.resolve_processccd_collections(
        _nickel_config(), "20230519"
    )
    assert got == [base]


def test_resolver_single_returns_newest_parent(pipeline_module, monkeypatch):
    older = "Nickel/runs/20230519/processCcd/20230101T000000Z"
    newer = "Nickel/runs/20230519/processCcd/20240101T000000Z"
    names = [older, f"{older}/run", newer, f"{newer}/run"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    # Default (all_parents=False) → only the newest parent.
    assert pipeline_module.resolve_processccd_collections(
        _nickel_config(), "20230519"
    ) == [newer]


def test_resolver_all_parents_newest_first(pipeline_module, monkeypatch):
    older = "Nickel/runs/20230519/processCcd/20230101T000000Z"
    newer = "Nickel/runs/20230519/processCcd/20240101T000000Z"
    names = [older, f"{older}/run", newer, f"{newer}/run_fb1"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    got = pipeline_module.resolve_processccd_collections(
        _nickel_config(), "20230519", all_parents=True
    )
    assert got == [newer, older]  # newest-first, run/run_fb excluded


def test_resolver_empty_when_no_collections(pipeline_module, monkeypatch):
    monkeypatch.setattr(
        pipeline_module.butler_query,
        "list_collections",
        lambda config, pattern, *, prefix=None: [],
    )
    assert (
        pipeline_module.resolve_processccd_collections(_nickel_config(), "20230519")
        == []
    )


# --------------------------------------------------------------------------- #
# resolve_processccd_collections — fallback (no CHAINED parent) path
# --------------------------------------------------------------------------- #
def test_resolver_fallback_prefers_run_over_run_fb(
    pipeline_module, monkeypatch, caplog
):
    # Only bare RUNs exist (no CHAINED parent). /run wins over a lone /run_fb1,
    # and a WARNING is emitted. This is the buggy tie-break the old code got
    # wrong (sorted()[-1] would pick /run_fb1, sorting after /run).
    base = "Nickel/runs/20230519/processCcd/ts1"
    names = [f"{base}/run", f"{base}/run_fb1"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    import logging

    with caplog.at_level(logging.WARNING):
        got = pipeline_module.resolve_processccd_collections(
            _nickel_config(), "20230519"
        )
    assert got == [f"{base}/run"]
    assert any("falling back to bare RUN" in r.message for r in caplog.records)


def test_resolver_fallback_uses_run_fb_when_no_run(pipeline_module, monkeypatch):
    base = "Nickel/runs/20230519/processCcd/ts1"
    names = [f"{base}/run_fb2", f"{base}/run_fb1"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    got = pipeline_module.resolve_processccd_collections(
        _nickel_config(), "20230519"
    )
    # Newest-first among the fallback RUNs.
    assert got == [f"{base}/run_fb2"]


# --------------------------------------------------------------------------- #
# resolve_processccd_collections — verify_datasets (coadd behavior)
# --------------------------------------------------------------------------- #
def test_resolver_verify_datasets_filters(pipeline_module, monkeypatch):
    older = "Nickel/runs/20230519/processCcd/20230101T000000Z"
    newer = "Nickel/runs/20230519/processCcd/20240101T000000Z"
    names = [older, f"{older}/run", newer, f"{newer}/run"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    # Newest parent lacks the requested band; older parent has it.
    monkeypatch.setattr(
        pipeline_module.butler_query,
        "has_datasets",
        lambda config, dataset_type, collection, *, where="": collection == older,
    )
    got = pipeline_module.resolve_processccd_collections(
        _nickel_config(),
        "20230519",
        verify_datasets=True,
        dataset_type="preliminary_visit_image",
        where="band='r'",
    )
    assert got == [older]


def test_resolver_verify_datasets_empty_when_none_match(pipeline_module, monkeypatch):
    base = "Nickel/runs/20230519/processCcd/ts1"
    names = [base, f"{base}/run"]
    monkeypatch.setattr(
        pipeline_module.butler_query, "list_collections", _fake_list(names)
    )
    monkeypatch.setattr(
        pipeline_module.butler_query,
        "has_datasets",
        lambda *a, **k: False,
    )
    got = pipeline_module.resolve_processccd_collections(
        _nickel_config(),
        "20230519",
        verify_datasets=True,
        dataset_type="preliminary_visit_image",
        where="band='r'",
    )
    assert got == []


def test_resolver_verify_datasets_requires_dataset_type(pipeline_module):
    with pytest.raises(ValueError, match="dataset_type"):
        pipeline_module.resolve_processccd_collections(
            _nickel_config(), "20230519", verify_datasets=True
        )


# --------------------------------------------------------------------------- #
# fphot image_type validation (F-049)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["diff", "difference", "", "Visit"])
def test_fphot_rejects_invalid_image_type(fphot_module, bad):
    from unittest import mock

    result = fphot_module.run(
        "20230519",
        210.9,
        54.3,
        config=mock.Mock(),
        image_type=bad,
    )
    assert result.success is False
    assert "image_type" in (result.error or "")


def test_fphot_valid_image_types_constant(fphot_module):
    assert fphot_module.VALID_IMAGE_TYPES == {"visit", "diffim", "both"}
