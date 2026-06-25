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
