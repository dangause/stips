from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from nickel_refcats import gaia

GAIA_COLS = [
    "source_id",
    "ra",
    "dec",
    "ra_error",
    "dec_error",
    "pmra",
    "pmdec",
    "pmra_error",
    "pmdec_error",
    "parallax",
    "parallax_error",
    "ref_epoch",
    "phot_g_mean_mag",
    "phot_bp_mean_mag",
    "phot_rp_mean_mag",
]


def _fake_results():
    return pd.DataFrame({c: np.array([1.0, 2.0]) for c in GAIA_COLS})


def test_fetch_gaia_cone_writes_required_columns(tmp_path: Path):
    out = tmp_path / "gaia.csv"
    job = mock.Mock()
    job.get_results.return_value = _fake_results()
    with mock.patch.object(gaia, "_launch_gaia_job", return_value=job) as launch:
        result = gaia.fetch_gaia_cone(210.91, 54.31, 0.3, out_csv=out)
    assert result == out
    launch.assert_called_once()
    df = pd.read_csv(out)
    for col in ["ra", "dec", "pmra", "pmdec", "ref_epoch"]:
        assert col in df.columns


def test_cone_adql_includes_quality_cuts():
    adql = gaia._build_cone_adql(10.0, 20.0, 0.3, ruwe_max=1.4, require_5param=True)
    assert (
        "CONTAINS" in adql
        and "CIRCLE('ICRS', 10.00000000, 20.00000000, 0.30000000)" in adql
    )
    assert "g.ruwe < 1.400" in adql
    assert "g.pmra IS NOT NULL" in adql


def test_cone_adql_omits_cuts_when_disabled():
    adql = gaia._build_cone_adql(10.0, 20.0, 0.3, ruwe_max=None, require_5param=False)
    assert "ruwe" not in adql
    assert "IS NOT NULL" not in adql
