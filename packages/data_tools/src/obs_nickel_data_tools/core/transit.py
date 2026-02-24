"""Transit search and parameter extraction for exoplanet lightcurves.

Implements Box Least Squares (BLS) periodogram analysis on lightcurves
extracted by the Nickel Processing Suite pipeline. Reads CSV output from
extract_lightcurve.py, performs multi-band transit search with per-band
baseline normalization, and produces BLS periodogram + phase-folded transit
plots with model overlay.

Scientific basis:
    - BLS periodogram: Kovacs, Zucker & Mazeh (2002)
    - Implementation: astropy.timeseries.BoxLeastSquares

Dependencies (all in LSST stack):
    - astropy.timeseries.BoxLeastSquares
    - numpy
    - matplotlib
    - pandas
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Band display colours for phase-folded plot
_BAND_COLORS: dict[str, str] = {
    "b": "blue",
    "v": "green",
    "r": "red",
    "i": "darkred",
}

# Required columns in the lightcurve CSV
_REQUIRED_COLUMNS = {"mjd", "band", "flux", "flux_err"}


@dataclass
class TransitResult:
    """Result of a BLS transit search.

    Attributes
    ----------
    best_period : float
        Orbital period (days) at the highest BLS power.
    t0 : float
        MJD of first transit midpoint.
    duration : float
        Transit duration in hours.
    depth : float
        Fractional transit depth (e.g., 0.01 = 1% dip).
    depth_err : float
        Uncertainty on transit depth.
    transit_snr : float
        Transit signal-to-noise ratio (depth / depth_err).
    periods : np.ndarray
        Full period grid used for BLS.
    powers : np.ndarray
        BLS power values over the period grid.
    phase_folded : dict
        Per-band phase-folded data: {band: {phase, flux_norm, flux_err}}.
    transit_model : dict
        Model for plot overlay: {phase, model_flux}.
    output_dir : Path
        Directory where plots and JSON results were written.
    """

    best_period: float
    t0: float
    duration: float  # hours
    depth: float
    depth_err: float
    transit_snr: float
    periods: np.ndarray
    powers: np.ndarray
    phase_folded: dict = field(default_factory=dict)
    transit_model: dict = field(default_factory=dict)
    output_dir: Path = field(default_factory=lambda: Path("."))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_lightcurve(csv_path: Path) -> pd.DataFrame:
    """Read a lightcurve CSV and return a sorted DataFrame.

    Parameters
    ----------
    csv_path : Path
        Path to the CSV file produced by extract_lightcurve.py.

    Returns
    -------
    pd.DataFrame
        Rows sorted by MJD.

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    df = pd.read_csv(csv_path)
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Lightcurve CSV missing required columns: {missing}")
    df = df.sort_values("mjd").reset_index(drop=True)
    return df


def _normalize_to_baseline(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Normalize flux to per-band baseline (fractional units).

    Divides each band's flux by its median, producing values near 1.0
    for out-of-transit points and < 1.0 during transit.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve DataFrame with at least 'band', 'flux', 'flux_err'.

    Returns
    -------
    norm_flux : np.ndarray
        Baseline-normalized flux values (1.0 = baseline).
    norm_err : np.ndarray
        Normalized flux error values.
    """
    flux = df["flux"].to_numpy(dtype=float).copy()
    flux_err = df["flux_err"].to_numpy(dtype=float).copy()
    for band in df["band"].unique():
        mask = df["band"] == band
        median = np.median(flux[mask])
        if median != 0:
            flux[mask] /= median
            flux_err[mask] /= abs(median)
    return flux, flux_err


def _run_bls(
    df: pd.DataFrame,
    *,
    period_min: float,
    period_max: float,
    duration_min: float,
    duration_max: float,
    n_samples: int,
) -> TransitResult:
    """Compute a BLS periodogram and extract transit parameters.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve data (mjd, band, flux, flux_err).
    period_min : float
        Minimum period to search (days).
    period_max : float
        Maximum period to search (days).
    duration_min : float
        Minimum transit duration (hours).
    duration_max : float
        Maximum transit duration (hours).
    n_samples : int
        Number of period samples.

    Returns
    -------
    TransitResult
        Populated except for phase_folded, transit_model, and output_dir.
    """
    from astropy import units as u
    from astropy.timeseries import BoxLeastSquares

    times = df["mjd"].to_numpy(dtype=float)
    norm_flux, norm_err = _normalize_to_baseline(df)

    # BLS periodogram
    bls = BoxLeastSquares(times * u.day, norm_flux, norm_err)
    periods = np.linspace(period_min, period_max, n_samples) * u.day
    durations = np.linspace(duration_min / 24.0, duration_max / 24.0, 10) * u.day

    results = bls.power(periods, durations)

    best_idx = int(np.argmax(results.power))
    best_period = float(results.period[best_idx].value)
    best_duration = float(results.duration[best_idx].to(u.hour).value)
    best_t0 = float(results.transit_time[best_idx].value)

    # Extract transit depth from the BLS model stats
    # stats["depth"] is a (depth, depth_uncertainty) tuple
    stats = bls.compute_stats(
        best_period * u.day,
        best_duration / 24.0 * u.day,
        best_t0 * u.day,
    )
    depth = float(stats["depth"][0])
    depth_err = float(stats["depth"][1])
    if depth_err <= 0:
        depth_err = abs(depth) * 0.1 if depth != 0 else 1e-10
    transit_snr = abs(depth) / depth_err if depth_err > 0 else 0.0

    return TransitResult(
        best_period=best_period,
        t0=best_t0,
        duration=best_duration,
        depth=depth,
        depth_err=depth_err,
        transit_snr=transit_snr,
        periods=np.array([p.value for p in results.period]),
        powers=np.array(results.power),
    )


def _phase_fold_transit(
    df: pd.DataFrame, period: float, t0: float
) -> dict[str, dict[str, np.ndarray]]:
    """Phase-fold the lightcurve centered on mid-transit.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve data with mjd, band, flux, flux_err.
    period : float
        Orbital period in days.
    t0 : float
        MJD of transit midpoint.

    Returns
    -------
    dict[str, dict[str, np.ndarray]]
        Per-band dict with keys 'phase', 'flux_norm', 'flux_err'.
        Phase is in range [-0.5, 0.5] with 0.0 at mid-transit.
    """
    mjds = df["mjd"].to_numpy(dtype=float)
    norm_flux, norm_err = _normalize_to_baseline(df)

    # Phase centered on t0, range [-0.5, 0.5]
    phase_all = ((mjds - t0) / period + 0.5) % 1.0 - 0.5

    result: dict[str, dict[str, np.ndarray]] = {}
    for band in df["band"].unique():
        mask = (df["band"] == band).to_numpy()
        result[band] = {
            "phase": phase_all[mask],
            "flux_norm": norm_flux[mask],
            "flux_err": norm_err[mask],
        }
    return result


def _make_transit_model(
    period: float, duration_hours: float, depth: float, n_points: int = 1000
) -> dict[str, np.ndarray]:
    """Generate a trapezoidal transit model for plot overlay.

    Parameters
    ----------
    period : float
        Orbital period in days.
    duration_hours : float
        Total transit duration in hours.
    depth : float
        Fractional transit depth.
    n_points : int
        Number of model phase points.

    Returns
    -------
    dict with 'phase' and 'model_flux' arrays.
    """
    phase = np.linspace(-0.5, 0.5, n_points)
    model_flux = np.ones_like(phase)

    # Transit half-duration in phase units
    half_dur_phase = (duration_hours / 24.0) / period / 2.0
    # Ingress/egress = 10% of total duration
    ingress_phase = half_dur_phase * 0.1

    for i, p in enumerate(phase):
        abs_p = abs(p)
        if abs_p < half_dur_phase - ingress_phase:
            # Full transit depth
            model_flux[i] = 1.0 - depth
        elif abs_p < half_dur_phase:
            # Ingress/egress ramp
            frac = (half_dur_phase - abs_p) / ingress_phase
            model_flux[i] = 1.0 - depth * frac

    return {"phase": phase, "model_flux": model_flux}
