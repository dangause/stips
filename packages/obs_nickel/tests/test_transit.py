#!/usr/bin/env python3
"""Unit tests for core/transit.py — BLS transit search and parameter extraction."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap (matches pattern in test_period.py)
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)

from obs_nickel_data_tools.core import transit as transit_mod  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_transit_signal(
    rng: np.random.Generator,
    mjds: np.ndarray,
    period: float,
    t0: float,
    depth: float,
    duration_days: float,
    baseline: float,
    noise: float,
) -> np.ndarray:
    """Generate a box-shaped transit signal with noise."""
    phase = ((mjds - t0) / period) % 1.0
    half_dur = (duration_days / period) / 2.0
    in_transit = (phase < half_dur) | (phase > 1.0 - half_dur)
    flux = np.full_like(mjds, baseline)
    flux[in_transit] *= 1.0 - depth
    flux += rng.normal(0, noise, len(mjds))
    return flux


@pytest.fixture()
def sample_transit_csv(tmp_path: Path):
    """Write a synthetic transit lightcurve: P=3.0d, depth=2%, duration=3h.

    100 points split between r- and i-bands over MJD 60000-60060.
    Returns (csv_path, true_period, true_depth, true_duration_hours).
    """
    rng = np.random.default_rng(42)
    true_period = 3.0
    true_depth = 0.02
    true_duration_hours = 3.0
    true_t0 = 60001.5
    duration_days = true_duration_hours / 24.0

    mjds = np.sort(rng.uniform(60000, 60060, 100))

    rows = []
    for i, mjd in enumerate(mjds):
        band = "r" if i % 2 == 0 else "i"
        baseline = 10000.0 if band == "r" else 8000.0
        flux_arr = _make_transit_signal(
            rng,
            np.array([mjd]),
            true_period,
            true_t0,
            true_depth,
            duration_days,
            baseline,
            noise=20.0,
        )
        rows.append(
            {
                "mjd": mjd,
                "band": band,
                "visit": 1000 + i,
                "ra": 30.0,
                "dec": 46.0,
                "flux": float(flux_arr[0]),
                "flux_err": 20.0,
                "mag": 18.0,
                "mag_err": 0.05,
                "snr": abs(float(flux_arr[0])) / 20.0,
                "separation_arcsec": 0.2,
            }
        )

    df = pd.DataFrame(rows)
    csv_path = tmp_path / "lightcurve.csv"
    df.to_csv(csv_path, index=False, float_format="%.6f")
    return csv_path, true_period, true_depth, true_duration_hours


# ---------------------------------------------------------------------------
# TestReadLightcurve
# ---------------------------------------------------------------------------


class TestReadLightcurve:
    def test_read_returns_dataframe(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 100

    def test_read_sorts_by_mjd(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        assert df["mjd"].is_monotonic_increasing

    def test_read_has_required_columns(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        for col in ("mjd", "band", "flux", "flux_err"):
            assert col in df.columns

    def test_read_raises_on_missing_columns(self, tmp_path):
        bad_csv = tmp_path / "bad.csv"
        pd.DataFrame({"mjd": [1], "band": ["r"]}).to_csv(bad_csv, index=False)
        with pytest.raises(ValueError, match="missing required columns"):
            transit_mod._read_lightcurve(bad_csv)
