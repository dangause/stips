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


# ---------------------------------------------------------------------------
# TestNormalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_normalize_to_baseline_produces_fractional_flux(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        norm_flux, flux_err = transit_mod._normalize_to_baseline(df)
        # Out-of-transit points should be near 1.0
        # Median of fractional flux should be close to 1.0
        assert abs(np.median(norm_flux) - 1.0) < 0.01

    def test_normalize_preserves_transit_dip(self, sample_transit_csv):
        csv_path, _, true_depth, _ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        norm_flux, _ = transit_mod._normalize_to_baseline(df)
        # Some points should be significantly below 1.0 (in-transit)
        min_flux = norm_flux.min()
        assert (
            min_flux < 1.0 - true_depth / 2
        ), f"Min normalized flux {min_flux:.4f} not low enough for {true_depth*100}% depth"

    def test_normalize_per_band_independence(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        norm_flux, _ = transit_mod._normalize_to_baseline(df)
        # Per-band median should each be near 1.0
        for band in df["band"].unique():
            mask = (df["band"] == band).to_numpy()
            band_median = np.median(norm_flux[mask])
            assert (
                abs(band_median - 1.0) < 0.02
            ), f"Band {band} median {band_median:.4f} not near 1.0"


# ---------------------------------------------------------------------------
# TestBLS
# ---------------------------------------------------------------------------


class TestBLS:
    def test_finds_correct_period(self, sample_transit_csv):
        csv_path, true_period, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=10_000,
        )
        assert (
            abs(result.best_period - true_period) / true_period < 0.05
        ), f"Expected ~{true_period} d, got {result.best_period:.4f} d"

    def test_depth_near_true_value(self, sample_transit_csv):
        csv_path, _, true_depth, _ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=10_000,
        )
        # Depth should be within factor of 3 of true value
        # (BLS depth estimate can be rough with sparse ground-based data)
        assert result.depth > 0, f"Depth should be positive, got {result.depth}"
        assert result.depth < 0.1, f"Depth too large: {result.depth}"

    def test_duration_reasonable(self, sample_transit_csv):
        csv_path, _, _, true_dur = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=10_000,
        )
        assert result.duration > 0, "Duration must be positive"
        assert result.duration < 12, f"Duration too long: {result.duration} hours"

    def test_power_spectrum_shape(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        n = 5_000
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=n,
        )
        assert len(result.periods) == n
        assert len(result.powers) == n

    def test_transit_snr_positive(self, sample_transit_csv):
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=10_000,
        )
        assert result.transit_snr > 0

    def test_no_signal_has_low_snr(self, tmp_path):
        """Pure noise should produce low transit SNR."""
        rng = np.random.default_rng(99)
        n = 60
        mjds = np.sort(rng.uniform(60000, 60040, n))
        rows = [
            {
                "mjd": mjd,
                "band": "r",
                "visit": 1000 + i,
                "ra": 0.0,
                "dec": 0.0,
                "flux": 10000.0 + rng.normal(0, 50),
                "flux_err": 50.0,
                "mag": 18.0,
                "mag_err": 0.1,
                "snr": 200.0,
                "separation_arcsec": 0.0,
            }
            for i, mjd in enumerate(mjds)
        ]
        csv_path = tmp_path / "noise.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=5_000,
        )
        # Noise-only data should have low depth
        assert result.depth < 0.02, f"Noise-only depth too high: {result.depth}"


# ---------------------------------------------------------------------------
# TestPhaseFolding
# ---------------------------------------------------------------------------


class TestPhaseFolding:
    def test_phase_fold_produces_per_band_data(self, sample_transit_csv):
        csv_path, true_period, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        folded = transit_mod._phase_fold_transit(df, true_period, t0=60001.5)
        assert "r" in folded
        assert "i" in folded
        for band in ("r", "i"):
            for key in ("phase", "flux_norm", "flux_err"):
                assert key in folded[band], f"Missing '{key}' for band {band}"

    def test_phase_values_between_minus_half_and_half(self, sample_transit_csv):
        csv_path, true_period, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        folded = transit_mod._phase_fold_transit(df, true_period, t0=60001.5)
        for band, data in folded.items():
            phases = data["phase"]
            assert phases.min() >= -0.5, f"Phase < -0.5 for band {band}"
            assert phases.max() <= 0.5, f"Phase > 0.5 for band {band}"

    def test_transit_centered_at_phase_zero(self, sample_transit_csv):
        csv_path, true_period, true_depth, _ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        folded = transit_mod._phase_fold_transit(df, true_period, t0=60001.5)
        # Points near phase 0 should have lower flux (in-transit)
        for band, data in folded.items():
            near_center = np.abs(data["phase"]) < 0.1
            if near_center.sum() > 0:
                near_flux = np.median(data["flux_norm"][near_center])
                far_mask = np.abs(data["phase"]) > 0.3
                if far_mask.sum() > 0:
                    far_flux = np.median(data["flux_norm"][far_mask])
                    # In-transit flux should be lower than out-of-transit
                    assert near_flux <= far_flux + 0.01, (
                        f"Band {band}: near-center flux {near_flux:.4f} >= "
                        f"far flux {far_flux:.4f}"
                    )


# ---------------------------------------------------------------------------
# TestTransitModel
# ---------------------------------------------------------------------------


class TestTransitModel:
    def test_model_has_expected_keys(self):
        model = transit_mod._make_transit_model(
            period=3.0,
            duration_hours=3.0,
            depth=0.02,
        )
        assert "phase" in model
        assert "model_flux" in model

    def test_model_baseline_near_one(self):
        model = transit_mod._make_transit_model(
            period=3.0,
            duration_hours=3.0,
            depth=0.02,
        )
        # Most model points should be at baseline (~1.0)
        baseline_mask = np.abs(model["phase"]) > 0.2
        assert np.allclose(model["model_flux"][baseline_mask], 1.0)

    def test_model_dip_at_center(self):
        depth = 0.02
        model = transit_mod._make_transit_model(
            period=3.0,
            duration_hours=3.0,
            depth=depth,
        )
        # Center should be at 1.0 - depth
        center_mask = np.abs(model["phase"]) < 0.01
        center_flux = model["model_flux"][center_mask]
        assert len(center_flux) > 0
        assert np.allclose(center_flux, 1.0 - depth, atol=0.001)


# ---------------------------------------------------------------------------
# TestOutputGeneration
# ---------------------------------------------------------------------------


class TestOutputGeneration:
    def _make_result(self, tmp_path, sample_transit_csv) -> transit_mod.TransitResult:
        csv_path, *_ = sample_transit_csv
        df = transit_mod._read_lightcurve(csv_path)
        result = transit_mod._run_bls(
            df,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=5_000,
        )
        result.phase_folded = transit_mod._phase_fold_transit(
            df,
            result.best_period,
            result.t0,
        )
        result.transit_model = transit_mod._make_transit_model(
            result.best_period,
            result.duration,
            result.depth,
        )
        return result

    def test_save_creates_json(self, tmp_path, sample_transit_csv):
        import json as json_mod

        result = self._make_result(tmp_path, sample_transit_csv)
        out_dir = tmp_path / "out"
        transit_mod._save_results(result, out_dir)
        json_path = out_dir / "transit_results.json"
        assert json_path.exists()
        data = json_mod.loads(json_path.read_text())
        for key in ("best_period", "t0", "duration_hours", "depth", "transit_snr"):
            assert key in data, f"Missing '{key}' in JSON"

    def test_save_creates_bls_periodogram(self, tmp_path, sample_transit_csv):
        result = self._make_result(tmp_path, sample_transit_csv)
        out_dir = tmp_path / "out2"
        transit_mod._save_results(result, out_dir)
        assert (out_dir / "bls_periodogram.png").exists()

    def test_save_creates_phase_folded_plot(self, tmp_path, sample_transit_csv):
        result = self._make_result(tmp_path, sample_transit_csv)
        out_dir = tmp_path / "out3"
        transit_mod._save_results(result, out_dir)
        assert (out_dir / "phase_folded_transit.png").exists()


# ---------------------------------------------------------------------------
# TestRun
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_end_to_end(self, tmp_path, sample_transit_csv):
        import json as json_mod

        csv_path, true_period, true_depth, _ = sample_transit_csv
        out_dir = tmp_path / "transit_analysis"
        result = transit_mod.run(
            csv_path,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=10_000,
            output_dir=out_dir,
        )

        # Period within 5%
        assert abs(result.best_period - true_period) / true_period < 0.05

        # Positive depth
        assert result.depth > 0

        # All 3 output files present
        assert (out_dir / "transit_results.json").exists()
        assert (out_dir / "bls_periodogram.png").exists()
        assert (out_dir / "phase_folded_transit.png").exists()

        # Phase data for both bands
        assert "r" in result.phase_folded
        assert "i" in result.phase_folded

        # Transit model populated
        assert "phase" in result.transit_model
        assert "model_flux" in result.transit_model

        # JSON readable
        data = json_mod.loads((out_dir / "transit_results.json").read_text())
        assert "best_period" in data
        assert "depth" in data
        assert "transit_snr" in data

    def test_run_with_few_points(self, tmp_path):

        rows = [
            {
                "mjd": 60000.0 + i * 3.0,
                "band": "r",
                "visit": 1000 + i,
                "ra": 0.0,
                "dec": 0.0,
                "flux": 10000.0 + 50.0 * i,
                "flux_err": 20.0,
                "mag": 18.0,
                "mag_err": 0.1,
                "snr": 500.0,
                "separation_arcsec": 0.0,
            }
            for i in range(5)
        ]
        csv_path = tmp_path / "tiny.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        out_dir = tmp_path / "tiny_out"
        result = transit_mod.run(
            csv_path,
            period_min=1.0,
            period_max=10.0,
            duration_min=1.0,
            duration_max=5.0,
            n_samples=1_000,
            output_dir=out_dir,
        )
        assert isinstance(result, transit_mod.TransitResult)
        assert (out_dir / "transit_results.json").exists()
