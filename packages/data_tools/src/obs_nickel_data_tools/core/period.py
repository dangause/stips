"""Period search and phase folding for variable star lightcurves.

Implements Lomb-Scargle periodogram analysis on lightcurves extracted by
the Nickel Processing Suite pipeline. Reads CSV output from
extract_lightcurve.py, performs multi-band period search with per-band
flux normalization, and produces periodogram + phase-folded plots.

Scientific basis:
    - Lomb-Scargle periodogram: Lomb (1976), Scargle (1982)
    - False alarm probability: Baluev (2008) analytic method
    - Implementation: astropy.timeseries.LombScargle

Dependencies (all in LSST stack):
    - astropy.timeseries.LombScargle
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
class PeriodResult:
    """Result of a Lomb-Scargle period search.

    Attributes
    ----------
    best_period : float
        Period (days) at the highest Lomb-Scargle power.
    best_frequency : float
        Corresponding frequency (1/days).
    power : float
        Lomb-Scargle power at the best period.
    fap : float
        False alarm probability via the Baluev (2008) analytic method.
    periods : np.ndarray
        Full period grid used for the periodogram.
    powers : np.ndarray
        Lomb-Scargle power values over the period grid.
    phase_folded : dict
        Per-band phase-folded data: {band: {phase, flux, flux_err}}.
    output_dir : Path
        Directory where plots and JSON results were written.
    """

    best_period: float
    best_frequency: float
    power: float
    fap: float
    periods: np.ndarray
    powers: np.ndarray
    phase_folded: dict = field(default_factory=dict)
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
        Rows sorted by MJD, columns include at least mjd, band, flux,
        flux_err.

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


def _normalize_flux_per_band(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Subtract the per-band mean flux for multi-band Lomb-Scargle.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve DataFrame with at least 'band', 'flux', 'flux_err'.

    Returns
    -------
    norm_flux : np.ndarray
        Mean-subtracted flux values aligned with df rows.
    flux_err : np.ndarray
        Flux error values aligned with df rows.
    """
    norm_flux = df["flux"].to_numpy(dtype=float).copy()
    for band in df["band"].unique():
        mask = df["band"] == band
        norm_flux[mask] -= norm_flux[mask].mean()
    return norm_flux, df["flux_err"].to_numpy(dtype=float)


def _run_lomb_scargle(
    df: pd.DataFrame,
    *,
    period_min: float,
    period_max: float,
    n_samples: int,
) -> PeriodResult:
    """Compute a Lomb-Scargle periodogram over a uniform frequency grid.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve data (mjd, band, flux, flux_err).
    period_min : float
        Minimum period to search (days).
    period_max : float
        Maximum period to search (days).
    n_samples : int
        Number of frequency samples.

    Returns
    -------
    PeriodResult
        Populated except for phase_folded and output_dir.
    """
    from astropy.timeseries import LombScargle

    times = df["mjd"].to_numpy(dtype=float)
    norm_flux, flux_err = _normalize_flux_per_band(df)

    freq_min = 1.0 / period_max
    freq_max = 1.0 / period_min
    frequencies = np.linspace(freq_min, freq_max, n_samples)

    ls = LombScargle(times, norm_flux, flux_err)
    powers = ls.power(frequencies)

    best_idx = int(np.argmax(powers))
    best_freq = float(frequencies[best_idx])
    best_period = 1.0 / best_freq
    best_power = float(powers[best_idx])

    fap = float(ls.false_alarm_probability(best_power, method="baluev"))

    periods = 1.0 / frequencies

    return PeriodResult(
        best_period=best_period,
        best_frequency=best_freq,
        power=best_power,
        fap=fap,
        periods=periods,
        powers=powers,
    )


def _phase_fold(df: pd.DataFrame, period: float) -> dict[str, dict[str, np.ndarray]]:
    """Phase-fold the lightcurve at the given period.

    Parameters
    ----------
    df : pd.DataFrame
        Lightcurve data with mjd, band, flux, flux_err.
    period : float
        Folding period in days.

    Returns
    -------
    dict[str, dict[str, np.ndarray]]
        Per-band dict with keys 'phase', 'flux', 'flux_err'.
    """
    mjd_min = df["mjd"].min()
    phase_all = ((df["mjd"].to_numpy(dtype=float) - mjd_min) / period) % 1.0

    result: dict[str, dict[str, np.ndarray]] = {}
    for band in df["band"].unique():
        mask = (df["band"] == band).to_numpy()
        result[band] = {
            "phase": phase_all[mask],
            "flux": df["flux"].to_numpy(dtype=float)[mask],
            "flux_err": df["flux_err"].to_numpy(dtype=float)[mask],
        }
    return result


def _save_results(result: PeriodResult, output_dir: Path) -> None:
    """Write JSON summary, periodogram PNG, and phase-folded PNG.

    Parameters
    ----------
    result : PeriodResult
        Completed period result (phase_folded must be populated).
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
        "best_frequency": result.best_frequency,
        "power": result.power,
        "fap": result.fap,
        "n_bands": len(bands),
        "bands": bands,
    }
    json_path = output_dir / "period_results.json"
    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)
    log.info("Period results written to %s", json_path)

    # --- Periodogram --------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.periods, result.powers, lw=0.8, color="steelblue")
    ax.axvline(
        result.best_period,
        color="red",
        lw=1.5,
        linestyle="--",
        label=f"P = {result.best_period:.4f} d",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Period (days)")
    ax.set_ylabel("Lomb-Scargle Power")
    ax.set_title(f"FAP = {result.fap:.2e}")
    ax.legend(loc="best")
    fig.tight_layout()
    periodogram_path = output_dir / "periodogram.png"
    fig.savefig(periodogram_path)
    plt.close(fig)
    log.info("Periodogram saved to %s", periodogram_path)

    # --- Phase-folded -------------------------------------------------------
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    for band in sorted(result.phase_folded.keys()):
        data = result.phase_folded[band]
        color = _BAND_COLORS.get(band, "black")
        ax2.errorbar(
            data["phase"],
            data["flux"],
            yerr=data["flux_err"],
            fmt="o",
            color=color,
            label=f"{band.upper()}-band",
            markersize=5,
            capsize=2,
            alpha=0.8,
        )
    ax2.set_xlabel("Phase")
    ax2.set_ylabel("Flux")
    ax2.set_title(f"Phase-folded at P = {result.best_period:.4f} d")
    ax2.legend(loc="best")
    fig2.tight_layout()
    phase_path = output_dir / "phase_folded.png"
    fig2.savefig(phase_path)
    plt.close(fig2)
    log.info("Phase-folded plot saved to %s", phase_path)

    result.output_dir = output_dir


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    csv_path: Path,
    *,
    period_min: float = 0.1,
    period_max: float = 100.0,
    n_samples: int = 10_000,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> PeriodResult:
    """Run a full period search on a lightcurve CSV.

    Reads the lightcurve, performs a Lomb-Scargle period search, phase-folds
    at the best period, and writes periodogram.png, phase_folded.png, and
    period_results.json to output_dir.

    Parameters
    ----------
    csv_path : Path
        Path to the lightcurve CSV produced by extract_lightcurve.py.
    period_min : float
        Minimum search period in days (default: 0.1).
    period_max : float
        Maximum search period in days (default: 100.0).
    n_samples : int
        Number of frequency grid points (default: 10 000).
    output_dir : Path or None
        Where to save results. Defaults to csv_path.parent/period_analysis.
    log_file : Path or None
        Optional path to append a file handler for this run's log messages.

    Returns
    -------
    PeriodResult
        Complete result including phase-folded data and output_dir.
    """
    csv_path = Path(csv_path)
    if output_dir is None:
        output_dir = csv_path.parent / "period_analysis"
    else:
        output_dir = Path(output_dir)

    # Optionally wire a file handler so callers can capture log output
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
        "Running Lomb-Scargle (period_min=%.2f d, period_max=%.2f d, n_samples=%d)",
        period_min,
        period_max,
        n_samples,
    )
    result = _run_lomb_scargle(
        df,
        period_min=period_min,
        period_max=period_max,
        n_samples=n_samples,
    )
    log.info(
        "Best period = %.4f d (f = %.4f /d), power = %.4f, FAP = %.2e",
        result.best_period,
        result.best_frequency,
        result.power,
        result.fap,
    )

    log.info("Phase-folding at P = %.4f d", result.best_period)
    result.phase_folded = _phase_fold(df, result.best_period)

    log.info("Saving results to %s", output_dir)
    _save_results(result, output_dir)

    return result
