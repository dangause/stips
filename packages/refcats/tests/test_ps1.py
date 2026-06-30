from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from nickel_refcats import ps1

PS1_COLS = [
    "objID",
    "raMean",
    "decMean",
    "raMeanErr",
    "decMeanErr",
    "epochMean",
    "gMeanPSFMag",
    "rMeanPSFMag",
    "iMeanPSFMag",
    "zMeanPSFMag",
    "yMeanPSFMag",
    "gMeanPSFMagErr",
    "rMeanPSFMagErr",
    "iMeanPSFMagErr",
    "zMeanPSFMagErr",
    "yMeanPSFMagErr",
    "nDetections",
    "ng",
    "nr",
    "ni",
    "nz",
    "ny",
    "qualityFlag",
    "objInfoFlag",
]


def _rows(specs):
    """Build a PS1-shaped DataFrame; specs sets g/r/i/z per row, rest = 1.0."""
    df = pd.DataFrame({c: np.full(len(specs), 1.0) for c in PS1_COLS})
    for i, s in enumerate(specs):
        for band, val in s.items():
            df.loc[i, band] = val
    return df


def test_fetch_ps1_cone_drops_objects_without_gri_psf_mags(tmp_path: Path):
    out = tmp_path / "ps1.csv"
    df = _rows(
        [
            {"gMeanPSFMag": 18.0, "rMeanPSFMag": 18.2, "iMeanPSFMag": 18.1},  # keep
            {"gMeanPSFMag": -999.0},  # drop: no g PSF mag
            {"iMeanPSFMag": -999.0},  # drop: no i PSF mag
        ]
    )
    with mock.patch.object(ps1, "_query_ps1_mean", return_value=df):
        ps1.fetch_ps1_cone(210.91, 54.31, 0.3, out_csv=out)
    got = pd.read_csv(out)
    # Only the fully-valid star survives; no mag-0/garbage-producing empties remain.
    assert len(got) == 1
    for col in ("gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag"):
        assert got[col].notna().all()
        assert (got[col] != -999.0).all()


def test_fetch_ps1_cone_keeps_star_missing_only_zy(tmp_path: Path):
    # z/y are not used by Nickel photometry, so a g/r/i-valid star is kept even
    # if z is missing (z masked to NaN; not required).
    out = tmp_path / "ps1.csv"
    df = _rows(
        [
            {
                "gMeanPSFMag": 18.0,
                "rMeanPSFMag": 18.2,
                "iMeanPSFMag": 18.1,
                "zMeanPSFMag": -999.0,
            }
        ]
    )
    with mock.patch.object(ps1, "_query_ps1_mean", return_value=df):
        ps1.fetch_ps1_cone(210.91, 54.31, 0.3, out_csv=out)
    got = pd.read_csv(out)
    assert len(got) == 1


def test_fetch_ps1_cone_skips_south_of_minus30(tmp_path: Path):
    with pytest.raises(ps1.PS1FootprintError):
        ps1.fetch_ps1_cone(50.0, -45.0, 0.3, out_csv=tmp_path / "x.csv")
