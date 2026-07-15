from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from stips_refcats import gaia

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


def test_fetch_gaia_cone_falls_back_to_sync_when_async_raises(tmp_path: Path):
    # Gaia's async TAP writes to a job-storage volume with periodic outages; the
    # sync path returns results inline and must take over transparently.
    out = tmp_path / "gaia.csv"
    sync_job = mock.Mock()
    sync_job.get_results.return_value = _fake_results()
    with (
        mock.patch.object(gaia, "_launch_gaia_job", side_effect=RuntimeError("500")),
        mock.patch.object(
            gaia, "_launch_gaia_job_sync", return_value=sync_job
        ) as launch_sync,
    ):
        result = gaia.fetch_gaia_cone(210.91, 54.31, 0.3, out_csv=out)
    assert result == out
    launch_sync.assert_called_once()
    assert "ra" in pd.read_csv(out).columns


def test_sync_adql_caps_rows_and_orders_by_brightness():
    # Pure string rewrite: no astroquery import (that costs ~69s and hits the
    # Gaia server -- the module defers it into _launch_gaia_job* on purpose).
    adql = gaia._build_cone_adql(10.0, 20.0, 0.3, ruwe_max=1.4, require_5param=True)
    sent = gaia._sync_adql(adql)
    assert sent.startswith("SELECT TOP 2000 ")
    assert sent.endswith(" ORDER BY g.phot_g_mean_mag")
    # The cap replaces only the leading SELECT, not any inside the WHERE clause.
    assert sent.count("SELECT TOP 2000 ") == 1
