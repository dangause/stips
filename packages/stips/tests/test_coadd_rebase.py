#!/usr/bin/env python3
"""Tests for coadd template build-then-swap sequencing (F-009).

These verify that ``core.coadd.run()`` never destroys an existing template
before a verified replacement exists:

* a failed build issues no chain-redefine / remove-collections against the old
  template (asserted by call order);
* a successful rebuild redefines the parent chain to the new RUN and *then*
  removes the superseded old RUNs;
* a failure while removing an old RUN is logged but does not flip the
  already-successful rebuild to a failure.

All Butler/pipetask calls are mocked, so no LSST stack is required.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def coadd_module():
    """Import the coadd module from the stips source tree."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from stips.core import coadd

    return coadd


def _config(tmp_path: Path) -> SimpleNamespace:
    """Minimal Config stub exposing a Nickel-like profile and a real repo path."""
    profile = SimpleNamespace(
        name="Nickel",
        collection_prefix="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
        instrument_class="lsst.obs.stips.active.Instrument",
    )
    return SimpleNamespace(
        repo=tmp_path,
        require_profile=lambda: profile,
        resolve_pipeline=lambda name: "DRP.yaml",
    )


class _Recorder:
    """Records ordered butler/pipetask invocations for call-order assertions."""

    def __init__(self):
        self.calls: list[tuple[str, str, list[str]]] = []
        # subcommand -> return code (default 0); pipetask_raises_on set separately
        self.butler_returncodes: dict[str, int] = {}

    def subcommands(self, kind: str | None = None) -> list[str]:
        return [
            sub for (k, sub, _args) in self.calls if kind is None or k == kind
        ]

    def args_for(self, sub: str) -> list[list[str]]:
        return [a for (_k, s, a) in self.calls if s == sub]


def _install(monkeypatch, coadd, recorder, *, pipetask_raises_on=None,
             verify_has_datasets=True, old_runs=None):
    """Wire up all mocks used by coadd.run() and return the recorder."""
    template_run_holder: dict[str, str] = {}

    def fake_run_butler(args, config, *, check=True, log_file=None, **kw):
        sub = args[0]
        recorder.calls.append(("butler", sub, list(args)))
        rc = recorder.butler_returncodes.get(sub, 0)
        return SimpleNamespace(returncode=rc)

    def fake_run_pipetask(args, config, *, log_file=None, **kw):
        sub = args[0]
        recorder.calls.append(("pipetask", sub, list(args)))
        if pipetask_raises_on == sub:
            raise RuntimeError(f"simulated pipetask {sub} failure")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(coadd, "run_butler", fake_run_butler)
    monkeypatch.setattr(coadd, "run_pipetask", fake_run_pipetask)
    monkeypatch.setattr(coadd, "generate_run_timestamp", lambda: "20260710T000000Z")
    monkeypatch.setattr(
        coadd,
        "find_science_collections_for_nights",
        lambda nights, band, config: ["Nickel/runs/20230101/processCcd/ts"],
    )
    monkeypatch.setattr(
        coadd, "find_degenerate_wcs_visits", lambda band, colls, config: []
    )

    def fake_list_collections(config, pattern, *, prefix=None):
        return list(old_runs or [])

    def fake_has_datasets(config, dataset_type, collection, *, where=""):
        return verify_has_datasets

    monkeypatch.setattr(coadd.butler_query, "list_collections", fake_list_collections)
    monkeypatch.setattr(coadd.butler_query, "has_datasets", fake_has_datasets)
    return template_run_holder


TRACT = 100
BAND = "r"
PARENT = f"templates/deep/tract{TRACT}/{BAND}"
NEW_RUN = f"{PARENT}/20260710T000000Z"
OLD_RUNS = [
    f"{PARENT}/20260101T000000Z",
    f"{PARENT}/20260102T000000Z",
]


def test_failed_build_leaves_old_template_untouched(coadd_module, monkeypatch, tmp_path):
    """A build that raises must not have redefined/removed the old template first."""
    rec = _Recorder()
    _install(monkeypatch, coadd_module, rec, pipetask_raises_on="run", old_runs=OLD_RUNS)

    result = coadd_module.run(
        ["20230101"], BAND, _config(tmp_path), tract=TRACT, overwrite=True
    )

    assert result.success is False
    # No destructive operations were issued against the existing template.
    assert "collection-chain" not in rec.subcommands("butler")
    assert "remove-collections" not in rec.subcommands("butler")
    # The build was attempted (register + qgraph + run) before it failed.
    assert rec.subcommands() == ["register-instrument", "qgraph", "run"]


def test_verified_empty_build_leaves_old_template_untouched(
    coadd_module, monkeypatch, tmp_path
):
    """A build that produces no template_coadd must not touch the old template."""
    rec = _Recorder()
    _install(
        monkeypatch,
        coadd_module,
        rec,
        verify_has_datasets=False,
        old_runs=OLD_RUNS,
    )

    result = coadd_module.run(
        ["20230101"], BAND, _config(tmp_path), tract=TRACT, overwrite=True
    )

    assert result.success is False
    assert "left untouched" in result.error
    assert "collection-chain" not in rec.subcommands("butler")
    assert "remove-collections" not in rec.subcommands("butler")


def test_successful_rebuild_swaps_chain_then_removes_old_runs(
    coadd_module, monkeypatch, tmp_path
):
    """Success path: redefine parent -> new RUN, then remove the old RUNs, in order."""
    rec = _Recorder()
    _install(monkeypatch, coadd_module, rec, old_runs=OLD_RUNS)

    result = coadd_module.run(
        ["20230101"], BAND, _config(tmp_path), tract=TRACT, overwrite=True
    )

    assert result.success is True
    assert result.collection == PARENT

    order = rec.subcommands()
    # Build fully precedes the chain swap, which precedes old-run removal.
    assert order.index("run") < order.index("collection-chain")
    assert order.index("collection-chain") < order.index("remove-collections")

    # The single swap redefines the parent chain to point at the NEW run.
    (chain_args,) = rec.args_for("collection-chain")
    assert chain_args == [
        "collection-chain",
        str(tmp_path),
        PARENT,
        NEW_RUN,
        "--mode",
        "redefine",
    ]

    # Each OLD run is removed (not the parent) after the swap.
    # remove-collections args == ["remove-collections", repo, run, "--no-confirm"]
    removed = [a[2] for a in rec.args_for("remove-collections")]
    assert removed == OLD_RUNS
    assert PARENT not in removed


def test_old_run_removal_failure_is_logged_but_still_succeeds(
    coadd_module, monkeypatch, tmp_path, caplog
):
    """A failure removing a superseded RUN is a WARNING, not a failed result."""
    rec = _Recorder()
    rec.butler_returncodes["remove-collections"] = 1  # every removal "fails"
    _install(monkeypatch, coadd_module, rec, old_runs=OLD_RUNS)

    with caplog.at_level(logging.WARNING):
        result = coadd_module.run(
            ["20230101"], BAND, _config(tmp_path), tract=TRACT, overwrite=True
        )

    assert result.success is True
    assert result.collection == PARENT
    # The chain was still swapped to the new run.
    assert "collection-chain" in rec.subcommands("butler")
    # Both removals were attempted and each logged a warning.
    assert len(rec.args_for("remove-collections")) == len(OLD_RUNS)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("Failed to remove superseded template run" in m for m in warnings)
