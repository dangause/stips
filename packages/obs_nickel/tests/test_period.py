#!/usr/bin/env python3
"""Unit tests for core/period.py — period search and phase folding."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap (matches pattern in test_fphot_collection_selection.py)
# ---------------------------------------------------------------------------
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)

from small_tel_tools.core import period as period_mod  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_lightcurve_csv(tmp_path: Path):
    """Write a synthetic 5-day sinusoidal lightcurve and return (path, true_period).

    60 points split evenly between r- and i-bands over MJD 60000-60050.
    Flux is sinusoidal with period 5.0 d plus Gaussian noise (seed 42).
    flux_err = 10.0 for all points.
    """
    rng = np.random.default_rng(42)
    true_period = 5.0

    mjds = rng.uniform(60000, 60050, 60)
    mjds.sort()

    rows = []
    for i, mjd in enumerate(mjds):
        if i % 2 == 0:
            band = "r"
            flux = 1000.0 + 100.0 * np.sin(2 * np.pi * mjd / true_period)
        else:
            band = "i"
            flux = 800.0 + 80.0 * np.sin(2 * np.pi * mjd / true_period)
        flux += rng.normal(0, 5.0)  # small noise so signal dominates
        rows.append(
            {
                "mjd": mjd,
                "band": band,
                "visit": 1000 + i,
                "ra": 210.91,
                "dec": 54.32,
                "flux": flux,
                "flux_err": 10.0,
                "mag": 18.0,
                "mag_err": 0.05,
                "snr": abs(flux) / 10.0,
                "separation_arcsec": 0.2,
            }
        )

    df = pd.DataFrame(rows)
    csv_path = tmp_path / "lightcurve.csv"
    df.to_csv(csv_path, index=False, float_format="%.6f")
    return csv_path, true_period


# ---------------------------------------------------------------------------
# TestReadLightcurve
# ---------------------------------------------------------------------------


class TestReadLightcurve:
    def test_read_lightcurve_returns_dataframe(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 60

    def test_read_lightcurve_sorts_by_mjd(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        assert df["mjd"].is_monotonic_increasing

    def test_read_lightcurve_has_required_columns(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        for col in ("mjd", "band", "flux", "flux_err"):
            assert col in df.columns

    def test_normalize_flux_per_band(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        norm_flux, flux_err = period_mod._normalize_flux_per_band(df)
        for band in df["band"].unique():
            mask = df["band"] == band
            band_mean = norm_flux[mask.to_numpy()].mean()
            assert (
                abs(band_mean) < 1e-10
            ), f"Per-band mean not ~0 for band {band}: {band_mean}"


# ---------------------------------------------------------------------------
# TestLombScargle
# ---------------------------------------------------------------------------


class TestLombScargle:
    def test_finds_correct_period(self, sample_lightcurve_csv):
        csv_path, true_period = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        result = period_mod._run_lomb_scargle(
            df, period_min=0.5, period_max=50.0, n_samples=10_000
        )
        assert (
            abs(result.best_period - true_period) / true_period < 0.05
        ), f"Expected ~{true_period} d, got {result.best_period:.4f} d"

    def test_fap_is_low_for_real_signal(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        result = period_mod._run_lomb_scargle(
            df, period_min=0.5, period_max=50.0, n_samples=10_000
        )
        assert result.fap < 0.01, f"FAP too high for a clean signal: {result.fap}"

    def test_power_spectrum_shape(self, sample_lightcurve_csv):
        csv_path, _ = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        n = 5_000
        result = period_mod._run_lomb_scargle(
            df, period_min=0.5, period_max=50.0, n_samples=n
        )
        assert len(result.periods) == n
        assert len(result.powers) == n
        assert result.power == result.powers.max()

    def test_noise_only_has_high_fap(self, tmp_path: Path):
        rng = np.random.default_rng(99)
        n = 40
        mjds = np.sort(rng.uniform(60000, 60040, n))
        rows = [
            {
                "mjd": mjd,
                "band": "r",
                "visit": 1000 + i,
                "ra": 0.0,
                "dec": 0.0,
                "flux": rng.normal(1000, 50),
                "flux_err": 50.0,
                "mag": 18.0,
                "mag_err": 0.1,
                "snr": 20.0,
                "separation_arcsec": 0.0,
            }
            for i, mjd in enumerate(mjds)
        ]
        csv_path = tmp_path / "noise.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        df = period_mod._read_lightcurve(csv_path)
        result = period_mod._run_lomb_scargle(
            df, period_min=0.5, period_max=30.0, n_samples=5_000
        )
        assert (
            result.fap > 0.05
        ), f"Noise-only signal unexpectedly has low FAP: {result.fap}"


# ---------------------------------------------------------------------------
# TestPhaseFolding
# ---------------------------------------------------------------------------


class TestPhaseFolding:
    def test_phase_fold_produces_per_band_data(self, sample_lightcurve_csv):
        csv_path, true_period = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        folded = period_mod._phase_fold(df, true_period)
        assert "r" in folded
        assert "i" in folded
        for band in ("r", "i"):
            for key in ("phase", "flux", "flux_err"):
                assert key in folded[band], f"Missing key '{key}' for band {band}"

    def test_phase_values_between_0_and_1(self, sample_lightcurve_csv):
        csv_path, true_period = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        folded = period_mod._phase_fold(df, true_period)
        for band, data in folded.items():
            phases = data["phase"]
            assert phases.min() >= 0.0, f"Phase < 0 for band {band}"
            assert phases.max() < 1.0, f"Phase >= 1 for band {band}"


# ---------------------------------------------------------------------------
# TestOutputGeneration
# ---------------------------------------------------------------------------


class TestOutputGeneration:
    def _make_result(
        self, tmp_path: Path, sample_lightcurve_csv
    ) -> period_mod.PeriodResult:
        csv_path, true_period = sample_lightcurve_csv
        df = period_mod._read_lightcurve(csv_path)
        result = period_mod._run_lomb_scargle(
            df, period_min=0.5, period_max=50.0, n_samples=5_000
        )
        result.phase_folded = period_mod._phase_fold(df, result.best_period)
        return result

    def test_save_results_creates_json(self, tmp_path: Path, sample_lightcurve_csv):
        import json as json_mod

        result = self._make_result(tmp_path, sample_lightcurve_csv)
        out_dir = tmp_path / "out"
        period_mod._save_results(result, out_dir)
        json_path = out_dir / "period_results.json"
        assert json_path.exists(), "period_results.json not created"
        data = json_mod.loads(json_path.read_text())
        for key in ("best_period", "fap", "best_frequency"):
            assert key in data, f"Missing key '{key}' in JSON"

    def test_save_results_creates_periodogram_plot(
        self, tmp_path: Path, sample_lightcurve_csv
    ):
        result = self._make_result(tmp_path, sample_lightcurve_csv)
        out_dir = tmp_path / "out2"
        period_mod._save_results(result, out_dir)
        assert (out_dir / "periodogram.png").exists()

    def test_save_results_creates_phase_folded_plot(
        self, tmp_path: Path, sample_lightcurve_csv
    ):
        result = self._make_result(tmp_path, sample_lightcurve_csv)
        out_dir = tmp_path / "out3"
        period_mod._save_results(result, out_dir)
        assert (out_dir / "phase_folded.png").exists()


# ---------------------------------------------------------------------------
# TestRun
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_end_to_end(self, tmp_path: Path, sample_lightcurve_csv):
        import json as json_mod

        csv_path, true_period = sample_lightcurve_csv
        out_dir = tmp_path / "period_analysis"
        result = period_mod.run(
            csv_path,
            period_min=0.5,
            period_max=50.0,
            n_samples=10_000,
            output_dir=out_dir,
        )

        # Correct period within 5 %
        assert abs(result.best_period - true_period) / true_period < 0.05

        # Low FAP
        assert result.fap < 0.01

        # All 3 output files present
        assert (out_dir / "period_results.json").exists()
        assert (out_dir / "periodogram.png").exists()
        assert (out_dir / "phase_folded.png").exists()

        # Phase data for both bands
        assert "r" in result.phase_folded
        assert "i" in result.phase_folded

        # JSON readable with expected keys
        data = json_mod.loads((out_dir / "period_results.json").read_text())
        assert "best_period" in data
        assert "fap" in data

    def test_run_with_few_points_does_not_crash(self, tmp_path: Path):
        import json as json_mod

        # Only 3 r-band points — should not raise, should still produce JSON
        rows = [
            {
                "mjd": 60000.0 + i * 3.0,
                "band": "r",
                "visit": 1000 + i,
                "ra": 0.0,
                "dec": 0.0,
                "flux": 1000.0 + 50.0 * i,
                "flux_err": 20.0,
                "mag": 18.0,
                "mag_err": 0.1,
                "snr": 50.0,
                "separation_arcsec": 0.0,
            }
            for i in range(3)
        ]
        csv_path = tmp_path / "tiny.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        out_dir = tmp_path / "tiny_out"
        result = period_mod.run(
            csv_path,
            period_min=0.5,
            period_max=10.0,
            n_samples=1_000,
            output_dir=out_dir,
        )

        assert isinstance(result, period_mod.PeriodResult)
        json_path = out_dir / "period_results.json"
        assert json_path.exists()
        data = json_mod.loads(json_path.read_text())
        assert "best_period" in data
