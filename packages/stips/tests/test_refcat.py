from unittest import mock

from stips.core.refcat import RefcatResult, present_trixels


def test_present_trixels_parses_butler_ids():
    with mock.patch("stips.core.refcat._query_present_htm7", return_value={100, 101}):
        got = present_trixels(config=mock.Mock(), dataset_type="gaia_dr3")
    assert got == {100, 101}


def test_refcatresult_defaults():
    r = RefcatResult(mode="gaia_ps1")
    assert r.gaia_status is None and r.ps1_status is None
    assert r.collections == []


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
