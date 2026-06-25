from unittest import mock

from stips.core.refcat import RefcatResult, ensure_refcats, present_trixels


def _patch_all(monkeypatch, present_gaia, present_ps1):
    import stips.core.refcat as rc

    monkeypatch.setattr(rc, "cones_to_htm", lambda cones, depth=7: [100, 101, 102])
    monkeypatch.setattr(
        rc,
        "present_trixels",
        lambda config, dataset_type: (
            present_gaia if dataset_type == "gaia_dr3" else present_ps1
        ),
    )
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


def test_present_trixels_parses_butler_ids():
    with mock.patch("stips.core.refcat._query_present_htm7", return_value={100, 101}):
        got = present_trixels(config=mock.Mock(), dataset_type="gaia_dr3")
    assert got == {100, 101}


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
            config=mock.Mock(), name="gaia_dr3", ecsv_map="/tmp/filename_to_htm.ecsv"
        )
    joined = " ".join(" ".join(c) for c in calls)
    assert "register-dataset-type" in joined
    assert "ingest-files" in joined
    assert "collection-chain" in joined
    assert run_collection == "refcats/gaia_dr3"
