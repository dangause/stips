#!/usr/bin/env python3
"""Honest-accounting tests for science.run (audit F-026).

science.run must record an honest 0 plus a ``quanta_parse_failed`` marker (and
WARN) when pipetask exits 0 but the quanta summary cannot be parsed, instead of
fabricating a count of 1.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace


def _nickel_profile() -> SimpleNamespace:
    return SimpleNamespace(
        name="Nickel",
        collection_prefix="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
        instrument_class="lsst.obs.stips.active.Instrument",
        night_to_dayobs_offset_days=1,
    )


def test_science_rc0_unparseable_records_honest_zero(tmp_path, monkeypatch, caplog):
    from stips.core import processing_log, provenance, science

    profile = _nickel_profile()

    resolve = tmp_path / "resolved.py"
    resolve.write_text("# config\n")

    config = SimpleNamespace(
        repo=tmp_path,
        require_profile=lambda: profile,
        resolve_config=lambda name: resolve,
        resolve_pipeline=lambda name: tmp_path / "DRP.yaml",
    )

    calib = tmp_path / "primary.py"
    calib.write_text("# calibrateImage config\n")
    science_cfg = science.ScienceConfig(
        calibrate_image=calib,
        colorterms=resolve,
        calibrate_image_fallbacks=[],
        refcat_mode="monster",
    )

    # Executor: qgraph build + run both "succeed"; run exits 0 with output that
    # contains no parseable quanta summary.
    def fake_run_pipetask(args, cfg, **kwargs):
        return SimpleNamespace(returncode=0, stdout="pipetask done\n", stderr="")

    executor = SimpleNamespace(run_pipetask=fake_run_pipetask)

    # Stub out the stack/butler touchpoints.
    monkeypatch.setattr(science, "run_butler", lambda *a, **k: SimpleNamespace())
    monkeypatch.setattr(
        science.butler_query,
        "list_collections",
        lambda *a, **k: ["Nickel/raw/20230519/20230519T000000Z"],
    )
    monkeypatch.setattr(
        science.butler_query, "collection_exists", lambda *a, **k: True
    )
    monkeypatch.setattr(science, "_count_matching_exposures", lambda *a, **k: 3)
    # Summary file never written -> parse_summary_file returns None; force the
    # stdout/log regex fallback to also find nothing.
    monkeypatch.setattr(science, "parse_quanta_summary", lambda *a, **k: (0, 0))

    captured: dict[str, object] = {}

    def capture_save(plog, cfg):
        captured["plog"] = plog
        return tmp_path / "log.json"

    monkeypatch.setattr(processing_log, "save_log", capture_save)
    monkeypatch.setattr(provenance, "upsert_from_log", lambda *a, **k: None)

    caplog.set_level(logging.WARNING, logger=science.log.name)

    result = science.run(
        "20230519",
        config,
        skip_coadds=True,
        science_cfg=science_cfg,
        use_fallbacks=True,
        executor=executor,
    )

    # rc==0 is still success, but the count is the honest 0, not a fabricated 1.
    assert result.success is True
    assert result.quanta_succeeded == 0

    plog = captured["plog"]
    assert len(plog.configs_tried) == 1
    attempt = plog.configs_tried[0]
    assert attempt.quanta_succeeded == 0
    assert attempt.quanta_parse_failed is True

    assert any(
        "quanta_parse_failed=True" in rec.getMessage() for rec in caplog.records
    ), "expected a WARNING recording the parse failure"
