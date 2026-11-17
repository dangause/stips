"""A night's science selection is made once and shared by its band groups.

science.select_night() does the Butler work (raw collection, object and
coordinate exclusions, per-band counts); science.run(selection=...) must then
build exactly the data query it would have built itself, and must not query
the Butler again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from stips.core import science

NIGHT = "20230519"
RAW = "Nickel/raw/20230519/20230519T000000Z"


def _profile():
    return SimpleNamespace(
        name="Nickel",
        collection_prefix="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
        night_to_dayobs_offset_days=1,
    )


def _config(tmp_path):
    profile = _profile()
    resolved = tmp_path / "resolved.py"
    resolved.write_text("# config\n")
    return SimpleNamespace(
        repo=tmp_path,
        instrument_dir=tmp_path / "instruments" / "nickel",
        instrument_class="instruments.nickel.instrument.Instrument",
        require_profile=lambda: profile,
        resolve_config=lambda name: resolved,
        resolve_pipeline=lambda name: tmp_path / "DRP.yaml",
    )


def _science_cfg(tmp_path):
    calib = tmp_path / "primary.py"
    calib.write_text("# calibrateImage config\n")
    return science.ScienceConfig(
        calibrate_image=calib,
        colorterms=tmp_path / "resolved.py",
        calibrate_image_fallbacks=[],
        refcat_mode="monster",
    )


def _forbid(monkeypatch, *names):
    def boom(*a, **k):
        raise AssertionError("queried the Butler although a selection was given")

    for name in names:
        monkeypatch.setattr(science, name, boom)


def test_night_selection_counts_per_band():
    sel = science.NightSelection(RAW, "", "", {"rp": 18, "ip": 14})
    assert sel.count(["r", "i"]) == 0
    assert sel.count(["rp"]) == 18
    assert sel.count(["RP", "ip"]) == 32
    assert sel.count(None) == 32
    assert science.NightSelection(RAW, "", "", None).count(["r"]) is None


def test_select_night_queries_once_without_a_band_filter(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(science, "latest_raw_run", lambda c, n: RAW)
    monkeypatch.setattr(
        science,
        "_build_exclusions",
        lambda *a, **k: (" AND exposure.target_name='2023ixf'", " AND exposure NOT IN (7)"),
    )
    seen = {}

    def counts(cfg, where):
        seen["where"] = where
        return {"rp": 3}

    monkeypatch.setattr(science, "_count_exposures_by_band", counts)
    sel = science.select_night(config, NIGHT, object_filter="2023ixf", target_ra=1.0, target_dec=2.0)

    assert sel.raw_run == RAW
    assert sel.band_counts == {"rp": 3}
    assert "band IN" not in seen["where"]
    assert seen["where"] == (
        "instrument='Nickel' AND exposure.observation_type='science'"
        " AND day_obs IN (20230519, 20230520)"
        " AND exposure.target_name='2023ixf' AND exposure NOT IN (7)"
    )


def test_empty_band_group_fails_without_butler_queries(tmp_path, monkeypatch):
    _forbid(monkeypatch, "latest_raw_run", "_build_exclusions", "_count_matching_exposures")
    sel = science.NightSelection(RAW, "", "", {"rp": 18})
    executor = SimpleNamespace(run_pipetask=lambda *a, **k: pytest.fail("ran a pipetask"))

    result = science.run(
        NIGHT,
        _config(tmp_path),
        skip_coadds=True,
        science_cfg=_science_cfg(tmp_path),
        bands=["r", "i"],
        executor=executor,
        selection=sel,
    )

    assert result.success is False
    assert "No science exposures matched selection" in (result.error or "")


def test_selection_gives_the_same_data_query(tmp_path, monkeypatch):
    """With a selection, the graph is built from the very query run() builds itself."""
    object_expr = " AND exposure.target_name='2023ixf'"
    exclusion_expr = " AND exposure NOT IN (85521128)"
    monkeypatch.setattr(science, "_build_exclusions", lambda *a, **k: (object_expr, exclusion_expr))
    expected = science._build_data_query(
        _config(tmp_path),
        NIGHT,
        _profile(),
        bad_exposures=None,
        bad_file=None,
        object_filter="2023ixf",
        target_ra=1.0,
        target_dec=2.0,
        bands=["rp"],
    )

    captured = {}

    class Stop(Exception):
        pass

    def fake_attempts(ctx, *a, **k):
        captured["data_query"] = ctx.data_query
        captured["raw_run"] = ctx.raw_run
        raise Stop

    _forbid(monkeypatch, "latest_raw_run", "_build_exclusions", "_count_matching_exposures")
    monkeypatch.setattr(science, "ensure_instrument_registered", lambda *a, **k: None)
    monkeypatch.setattr(science, "_run_config_attempts", fake_attempts)

    with pytest.raises(Stop):
        science.run(
            NIGHT,
            _config(tmp_path),
            skip_coadds=True,
            science_cfg=_science_cfg(tmp_path),
            bands=["rp"],
            object_filter="2023ixf",
            target_ra=1.0,
            target_dec=2.0,
            executor=SimpleNamespace(),
            selection=science.NightSelection(RAW, object_expr, exclusion_expr, {"rp": 18}),
        )

    assert captured == {"data_query": expected, "raw_run": RAW}
