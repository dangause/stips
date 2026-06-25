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


def test_fetch_ps1_cone_masks_sentinel_and_writes_columns(tmp_path: Path):
    out = tmp_path / "ps1.csv"
    df = pd.DataFrame({c: np.array([10.0, -999.0]) for c in PS1_COLS})
    with mock.patch.object(ps1, "_query_ps1_mean", return_value=df):
        result = ps1.fetch_ps1_cone(210.91, 54.31, 0.3, out_csv=out)
    assert result == out
    got = pd.read_csv(out)
    for col in ["raMean", "decMean", "gMeanPSFMag", "rMeanPSFMag", "iMeanPSFMag"]:
        assert col in got.columns
    # -999.0 sentinel must be masked to NaN, not kept as a real magnitude.
    assert got["gMeanPSFMag"].isna().any()
    # Non-magnitude columns keep their values (sentinel only masked on mags/errs).
    assert (got["nDetections"] == -999.0).any()


def test_fetch_ps1_cone_skips_south_of_minus30(tmp_path: Path):
    with pytest.raises(ps1.PS1FootprintError):
        ps1.fetch_ps1_cone(50.0, -45.0, 0.3, out_csv=tmp_path / "x.csv")
