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

import json
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


def _save_results(result: TransitResult, output_dir: Path) -> None:
    """Write JSON summary, BLS periodogram PNG, and phase-folded transit PNG.

    Parameters
    ----------
    result : TransitResult
        Completed transit result (phase_folded and transit_model must be populated).
    output_dir : Path
        Destination directory (created if absent).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- JSON summary -------------------------------------------------------
    bands = sorted(result.phase_folded.keys())
    summary = {
        "best_period": result.best_period,
        "t0": result.t0,
        "duration_hours": result.duration,
        "depth": result.depth,
        "depth_err": result.depth_err,
        "transit_snr": result.transit_snr,
        "n_bands": len(bands),
        "bands": bands,
    }
    json_path = output_dir / "transit_results.json"
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    log.info("Transit results written to %s", json_path)

    # --- BLS Periodogram ----------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.periods, result.powers, lw=0.8, color="steelblue")
    ax.axvline(
        result.best_period,
        color="red",
        lw=1.5,
        linestyle="--",
        label=f"P = {result.best_period:.4f} d",
    )
    ax.set_xlabel("Period (days)")
    ax.set_ylabel("BLS Power")
    ax.set_title(f"Transit SNR = {result.transit_snr:.1f}")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_dir / "bls_periodogram.png")
    plt.close(fig)
    log.info("BLS periodogram saved to %s", output_dir / "bls_periodogram.png")

    # --- Phase-folded transit -----------------------------------------------
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    for band in sorted(result.phase_folded.keys()):
        data = result.phase_folded[band]
        color = _BAND_COLORS.get(band, "black")
        ax2.errorbar(
            data["phase"],
            data["flux_norm"],
            yerr=data["flux_err"],
            fmt="o",
            color=color,
            label=f"{band.upper()}-band",
            markersize=4,
            capsize=2,
            alpha=0.7,
        )
    # Overlay transit model
    if result.transit_model:
        ax2.plot(
            result.transit_model["phase"],
            result.transit_model["model_flux"],
            color="black",
            lw=2,
            alpha=0.8,
            label="Model",
        )
    ax2.set_xlabel("Orbital Phase")
    ax2.set_ylabel("Normalized Flux")
    ax2.set_title(
        f"P = {result.best_period:.4f} d, "
        f"depth = {result.depth * 100:.3f}%, "
        f"dur = {result.duration:.1f} h"
    )
    ax2.legend(loc="best")
    fig2.tight_layout()
    fig2.savefig(output_dir / "phase_folded_transit.png")
    plt.close(fig2)
    log.info(
        "Phase-folded transit saved to %s", output_dir / "phase_folded_transit.png"
    )

    result.output_dir = output_dir


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    csv_path: Path,
    *,
    period_min: float = 0.3,
    period_max: float = 30.0,
    duration_min: float = 0.5,
    duration_max: float = 6.0,
    n_samples: int = 10_000,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> TransitResult:
    """Run a full BLS transit search on a lightcurve CSV.

    Reads the lightcurve, runs a Box Least Squares transit search,
    phase-folds at the best period centered on mid-transit, and writes
    bls_periodogram.png, phase_folded_transit.png, and transit_results.json.

    Parameters
    ----------
    csv_path : Path
        Path to the lightcurve CSV produced by extract_lightcurve.py.
    period_min : float
        Minimum search period in days (default: 0.3).
    period_max : float
        Maximum search period in days (default: 30.0).
    duration_min : float
        Minimum transit duration in hours (default: 0.5).
    duration_max : float
        Maximum transit duration in hours (default: 6.0).
    n_samples : int
        Number of period grid points (default: 10 000).
    output_dir : Path or None
        Where to save results. Defaults to csv_path.parent/transit_analysis.
    log_file : Path or None
        Optional path to append a file handler for this run's log messages.

    Returns
    -------
    TransitResult
        Complete result including phase-folded data and output_dir.
    """
    csv_path = Path(csv_path)
    if output_dir is None:
        output_dir = csv_path.parent / "transit_analysis"
    else:
        output_dir = Path(output_dir)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, mode="a")
        fh.setLevel(logging.DEBUG)
        log.addHandler(fh)

    log.info("Reading lightcurve from %s", csv_path)
    df = _read_lightcurve(csv_path)
    log.info("Loaded %d rows across bands: %s", len(df), sorted(df["band"].unique()))

    log.info(
        "Running BLS (period_min=%.2f d, period_max=%.2f d, "
        "duration=%.1f-%.1f h, n_samples=%d)",
        period_min,
        period_max,
        duration_min,
        duration_max,
        n_samples,
    )
    result = _run_bls(
        df,
        period_min=period_min,
        period_max=period_max,
        duration_min=duration_min,
        duration_max=duration_max,
        n_samples=n_samples,
    )
    log.info(
        "Best period = %.4f d, depth = %.4f%%, duration = %.2f h, SNR = %.1f",
        result.best_period,
        result.depth * 100,
        result.duration,
        result.transit_snr,
    )

    log.info("Phase-folding at P = %.4f d, T0 = %.4f", result.best_period, result.t0)
    result.phase_folded = _phase_fold_transit(df, result.best_period, result.t0)

    log.info("Generating transit model")
    result.transit_model = _make_transit_model(
        result.best_period,
        result.duration,
        result.depth,
    )

    log.info("Saving results to %s", output_dir)
    _save_results(result, output_dir)

    return result
