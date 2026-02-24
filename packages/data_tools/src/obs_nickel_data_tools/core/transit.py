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
