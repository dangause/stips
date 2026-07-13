from unittest import mock

from stips.core.refcat import RefcatResult, ensure_refcats, present_trixels


def _patch_all(monkeypatch, present_gaia, present_ps1, requested=None):
    import stips.core.refcat as rc

    requested = requested or {}
    monkeypatch.setattr(rc, "cones_to_htm", lambda cones, depth=7: [100, 101, 102])
    monkeypatch.setattr(
        rc,
        "present_trixels",
        lambda config, dataset_type: (
            present_gaia if dataset_type == "gaia_dr3" else present_ps1
        ),
    )
    # Manifest helpers touch the filesystem; stub them (config is a Mock here).
    monkeypatch.setattr(rc, "_load_requested", lambda config: dict(requested))
    monkeypatch.setattr(rc, "_record_requested", lambda config, name, trixels: None)
    calls = {"gaia": 0, "ps1": 0, "convert": 0, "ingest": []}
    monkeypatch.setattr(
        rc,
        "fetch_gaia_cone",
        lambda *a, **k: calls.__setitem__("gaia", calls["gaia"] + 1) or "/tmp/g.csv",
    )
    monkeypatch.setattr(
        rc,
        "fetch_ps1_cone",
        lambda *a, **k: calls.__setitem__("ps1", calls["ps1"] + 1) or "/tmp/p.csv",
    )
    monkeypatch.setattr(
        rc,
        "convert_catalog",
        lambda *a, **k: calls.__setitem__("convert", calls["convert"] + 1)
        or "/tmp/map.ecsv",
    )
    monkeypatch.setattr(
        rc,
        "_ingest_refcat",
        lambda **k: calls["ingest"].append(k["name"]) or f"refcats/{k['name']}",
    )
    return calls


def test_ensure_refcats_noop_when_fully_covered(monkeypatch):
    calls = _patch_all(
        monkeypatch, present_gaia={100, 101, 102}, present_ps1={100, 101, 102}
    )
    r = ensure_refcats(config=mock.Mock(), ra=210.9, dec=54.3)
    assert r.gaia_status == "covered" and r.ps1_status == "covered"
    assert calls["gaia"] == 0 and calls["ps1"] == 0 and calls["ingest"] == []


def test_ensure_refcats_fetches_when_missing(monkeypatch):
    calls = _patch_all(monkeypatch, present_gaia=set(), present_ps1=set())
    r = ensure_refcats(config=mock.Mock(), ra=210.9, dec=54.3)
    assert r.gaia_status == "fetched" and r.ps1_status == "fetched"
    assert calls["gaia"] == 1 and calls["ps1"] == 1
    assert set(calls["ingest"]) == {"gaia_dr3", "panstarrs1_dr2"}


def test_ensure_refcats_skips_ps1_in_south(monkeypatch):
    import stips.core.refcat as rc

    _patch_all(monkeypatch, present_gaia=set(), present_ps1=set())

    def boom(*a, **k):
        raise rc.PS1FootprintError("south")

    monkeypatch.setattr(rc, "fetch_ps1_cone", boom)
    r = ensure_refcats(config=mock.Mock(), ra=50.0, dec=-45.0)
    assert r.gaia_status == "fetched"
    assert r.ps1_status == "skipped"


def test_ensure_refcats_monster_mode_is_noop(monkeypatch):
    calls = _patch_all(monkeypatch, present_gaia=set(), present_ps1=set())
    ensure_refcats(config=mock.Mock(), ra=210.9, dec=54.3, mode="monster")
    assert calls["gaia"] == 0 and calls["ps1"] == 0 and calls["convert"] == 0


def test_ensure_refcats_empty_trixels_covered_via_manifest(monkeypatch):
    # PS1 has shards for only 2 of 3 needed trixels (101 is legitimately empty),
    # but all 3 were previously requested -> must be treated as covered, no re-fetch.
    calls = _patch_all(
        monkeypatch,
        present_gaia={100, 101, 102},
        present_ps1={100, 102},
        requested={"panstarrs1_dr2": {100, 101, 102}},
    )
    r = ensure_refcats(config=mock.Mock(), ra=210.9, dec=54.3)
    assert r.ps1_status == "covered"
    assert calls["ps1"] == 0 and "panstarrs1_dr2" not in calls["ingest"]


def test_present_trixels_parses_butler_ids():
    with mock.patch("stips.core.refcat._query_present_htm7", return_value={100, 101}):
        got = present_trixels(config=mock.Mock(), dataset_type="gaia_dr3")
    assert got == {100, 101}


def test_query_present_htm7_uses_adapter():
    from stips.core import refcat

    cfg = mock.Mock()
    with mock.patch.object(
        refcat.butler_query,
        "dataset_data_id_values",
        return_value=[100, 101, 102],
    ) as m:
        got = refcat._query_present_htm7(cfg, "gaia_dr3")
    assert got == {100, 101, 102}
    # Delegates with the refcats collection and htm7 dimension.
    m.assert_called_once_with(cfg, "gaia_dr3", "refcats", "htm7")


def test_query_present_htm7_empty_when_none_present():
    from stips.core import refcat

    with mock.patch.object(
        refcat.butler_query, "dataset_data_id_values", return_value=[]
    ):
        got = refcat._query_present_htm7(mock.Mock(), "gaia_dr3")
    assert got == set()


def test_query_present_htm7_query_failure_returns_empty(caplog):
    from stips.core import refcat

    # Adapter returns None (in-stack query failed) -> empty set + a WARNING,
    # not a phantom "present" set that would skip the fetch.
    with mock.patch.object(
        refcat.butler_query, "dataset_data_id_values", return_value=None
    ):
        with caplog.at_level("WARNING"):
            got = refcat._query_present_htm7(mock.Mock(), "gaia_dr3")
    assert got == set()
    assert any("gaia_dr3" in rec.message for rec in caplog.records)


def test_refcatresult_defaults():
    r = RefcatResult(mode="gaia_ps1")
    assert r.gaia_status is None and r.ps1_status is None
    assert r.collections == []


def test_refcat_overlay_config_by_mode():
    from stips.core.refcat import refcat_overlay_config

    # Staging: DRP.yaml default is MONSTER, so monster needs no overlay.
    assert refcat_overlay_config("monster") is None
    assert refcat_overlay_config("gaia_ps1") == "refcats_gaia_ps1.py"


def test_ingest_refcat_runs_register_ingest_chain():
    from stips.core import refcat

    calls = []
    with mock.patch(
        "stips.core.refcat.run_butler",
        side_effect=lambda args, config, **k: calls.append(args),
    ):
        run_collection = refcat._ingest_refcat(
            config=mock.Mock(),
            name="gaia_dr3",
            ecsv_map="/tmp/filename_to_htm.ecsv",
            stamp="20260625T000000Z",
        )
    joined = " ".join(" ".join(c) for c in calls)
    assert "register-dataset-type" in joined
    assert "ingest-files" in joined
    assert "collection-chain" in joined
    # Timestamped RUN collection so re-fetches never collide on existing shards.
    assert run_collection == "refcats/gaia_dr3/20260625T000000Z"
    assert "refcats/gaia_dr3/20260625T000000Z" in joined


# --- _cones_to_htm_ids: venv-safe HTM coverage (in-process, else in-stack) ---


def test_cones_to_htm_ids_in_process(monkeypatch):
    import stips.core.refcat as rc

    monkeypatch.setattr(rc, "cones_to_htm", lambda cones, depth=7: [1, 2, 2])
    assert rc._cones_to_htm_ids(mock.Mock(), [(10.0, 20.0, 0.3)]) == {1, 2}


def test_cones_to_htm_ids_falls_back_to_stack(monkeypatch):
    import stips.core.refcat as rc

    def _no_lsst(cones, depth=7):
        raise ModuleNotFoundError("No module named 'lsst.geom'")

    captured = {}

    def _fake_json(script, config):
        captured["script"] = script
        return [100, 101]

    monkeypatch.setattr(rc, "cones_to_htm", _no_lsst)
    monkeypatch.setattr(rc, "run_butler_python_json", _fake_json)
    out = rc._cones_to_htm_ids(mock.Mock(), [(10.0, 20.0, 0.3)], depth=7)
    assert out == {100, 101}
    assert "HtmIndexer" in captured["script"]
    assert "(10.0, 20.0, 0.3)" in captured["script"]


def test_cones_to_htm_ids_raises_when_stack_helper_fails(monkeypatch):
    import pytest
    import stips.core.refcat as rc

    def _no_lsst(cones, depth=7):
        raise ModuleNotFoundError("No module named 'lsst.geom'")

    monkeypatch.setattr(rc, "cones_to_htm", _no_lsst)
    monkeypatch.setattr(rc, "run_butler_python_json", lambda script, config: None)
    with pytest.raises(RuntimeError, match="HTM coverage"):
        rc._cones_to_htm_ids(mock.Mock(), [(10.0, 20.0, 0.3)])
