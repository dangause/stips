# Variable Star Pipeline Extension Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add variable star period analysis capability to the Nickel Processing Suite with ~315 lines across 4 files.

**Architecture:** Extend the existing YAML-driven orchestrator (`core/run.py`) with new `pipeline_type` and `period_search` config fields that gate a new post-lightcurve period analysis step. The period analysis itself lives in a new self-contained module (`core/period.py`) that reads lightcurve CSVs and produces Lomb-Scargle periodograms + phase-folded plots. A sensitive DIA detection config file provides optional low-threshold source detection for variable star fields.

**Tech Stack:** Python 3.11+, astropy.timeseries.LombScargle, numpy, matplotlib, pandas, pytest, dataclasses

**Design doc:** `docs/plans/2026-02-19-variable-star-design.md`

---

## File Reference

All paths relative to repo root `/Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/`.

| Shorthand | Full Path |
|-----------|-----------|
| `core/run.py` | `packages/data_tools/src/obs_nickel_data_tools/core/run.py` |
| `core/period.py` | `packages/data_tools/src/obs_nickel_data_tools/core/period.py` |
| `detectAndMeasure_sensitive.py` | `packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py` |
| `detectAndMeasure.py` | `packages/obs_nickel/configs/dia/detectAndMeasure.py` |
| `extract_lightcurve.py` | `packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/extract_lightcurve.py` |
| `tests/` | `packages/obs_nickel/tests/` |
| `nickel_template.yaml` | `scripts/config/2023ixf/pipeline_nickel_template.yaml` |

---

### Task 1: Sensitive DIA Detection Config

The simplest change — a new config file for optional low-threshold DIA source detection.

**Files:**
- Create: `packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py`
- Reference: `packages/obs_nickel/configs/dia/detectAndMeasure.py` (existing SN config)

**Step 1: Create the sensitive detection config**

Write `packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py`:

```python
# ruff: noqa: F821
"""
Sensitive detection thresholds for low-amplitude variable star DIA sources.

Lowers the detection threshold from 3.0 sigma (supernova default) to 1.5 sigma
to capture subtle variability in difference images. Also reduces minPixels from
5 to 3 to detect smaller footprints from low-amplitude flux changes.

Note: This config is optional and only affects the DIA *source catalog*
(detectAndMeasure). Forced photometry at known RA/Dec coordinates measures flux
at the specified position regardless of detection threshold.

Usage in pipeline YAML:
    configs:
      dia:
        detect_and_measure: dia/detectAndMeasure_sensitive.py
"""

# Bad subtraction rejection (same as standard config)
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0

# Lower detection threshold for subtle variability
if hasattr(config, "detection"):
    config.detection.thresholdValue = 1.5  # sigma (vs 3.0 for SNe)
    config.detection.thresholdType = "stdev"
    config.detection.minPixels = 3  # smaller footprints (vs 5 for SNe)

# Enable sky sources and measurement when supported
if hasattr(config, "doSkySources"):
    config.doSkySources = True
if hasattr(config, "doMeasurement"):
    config.doMeasurement = True
if hasattr(config, "doWriteSubtractedExp"):
    config.doWriteSubtractedExp = True
```

**Step 2: Verify the file is valid Python**

Run: `python -c "exec(open('packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py').read().replace('config.', '# config.'))" && echo OK`

Expected: `OK` (no syntax errors)

**Step 3: Commit**

```bash
git add packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py
git commit -m "feat: add sensitive DIA detection config for variable stars

Lower detection threshold to 1.5 sigma (vs 3.0 for SNe) for
low-amplitude variable star difference image source detection."
```

---

### Task 2: PeriodResult Dataclass and CSV Reader (Test-First)

Build the data structures and CSV reading logic for the period module.

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/core/period.py`
- Create: `packages/obs_nickel/tests/test_period.py`

**Step 1: Write the failing test for PeriodResult and CSV reading**

Write `packages/obs_nickel/tests/test_period.py`:

```python
"""Tests for variable star period analysis module."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add data_tools source tree to path (same pattern as test_fphot_collection_selection.py)
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)


@pytest.fixture
def sample_lightcurve_csv(tmp_path):
    """Create a synthetic lightcurve CSV matching extract_lightcurve.py output format.

    Simulates a 5-day period sinusoidal variable observed over 50 days in r and i bands.
    CSV columns match extract_lightcurve.py output:
    mjd, band, visit, ra, dec, flux, flux_err, mag, mag_err, snr, separation_arcsec
    """
    np.random.seed(42)
    period = 5.0  # days
    n_points = 60
    mjds = np.sort(np.random.uniform(60000, 60050, n_points))
    bands = np.array(["r", "i"] * (n_points // 2))

    # Sinusoidal flux variation: amplitude 100 around mean 1000
    phase = 2 * np.pi * mjds / period
    flux_r = 1000 + 100 * np.sin(phase)
    flux_i = 800 + 80 * np.sin(phase)  # i-band slightly different mean/amp
    flux = np.where(bands == "r", flux_r, flux_i)
    flux_err = np.full(n_points, 10.0)
    snr = flux / flux_err

    # Write CSV
    csv_path = tmp_path / "lightcurve_test.csv"
    import csv

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "mjd", "band", "visit", "ra", "dec",
            "flux", "flux_err", "mag", "mag_err", "snr", "separation_arcsec",
        ])
        for i in range(n_points):
            writer.writerow([
                f"{mjds[i]:.6f}", bands[i], 80000000 + i,
                "210.910833", "54.316389",
                f"{flux[i]:.6f}", f"{flux_err[i]:.6f}",
                "20.0", "0.01", f"{snr[i]:.1f}", "0.15",
            ])

    return csv_path, period


class TestReadLightcurve:
    """Test CSV reading and band normalization."""

    def test_read_lightcurve_returns_dataframe(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _read_lightcurve

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)

        assert len(df) == 60
        assert "mjd" in df.columns
        assert "band" in df.columns
        assert "flux" in df.columns
        assert "flux_err" in df.columns

    def test_read_lightcurve_sorts_by_mjd(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _read_lightcurve

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)

        assert (df["mjd"].diff().dropna() >= 0).all()

    def test_normalize_flux_per_band(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _normalize_flux_per_band

        csv_path, _ = sample_lightcurve_csv
        import pandas as pd

        df = pd.read_csv(csv_path)
        norm_flux, norm_err = _normalize_flux_per_band(df)

        # After normalization, each band's mean flux should be ~0
        for band in df["band"].unique():
            mask = df["band"] == band
            assert abs(np.mean(norm_flux[mask])) < 1.0  # close to zero

        assert len(norm_flux) == len(df)
        assert len(norm_err) == len(df)
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestReadLightcurve -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'obs_nickel_data_tools.core.period'`

**Step 3: Write minimal implementation — CSV reader and normalization**

Write `packages/data_tools/src/obs_nickel_data_tools/core/period.py`:

```python
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


@dataclass
class PeriodResult:
    """Result of Lomb-Scargle period search."""

    best_period: float  # days
    best_frequency: float  # 1/days
    power: float  # Lomb-Scargle power at best period
    fap: float  # False alarm probability (Baluev method)
    periods: np.ndarray  # Full period grid
    powers: np.ndarray  # Full power spectrum
    phase_folded: dict = field(default_factory=dict)  # {band: {phase, flux, flux_err}}
    output_dir: Path = field(default_factory=lambda: Path("."))


def _read_lightcurve(csv_path: Path) -> pd.DataFrame:
    """Read lightcurve CSV produced by extract_lightcurve.py.

    Expected columns: mjd, band, visit, ra, dec, flux, flux_err, mag,
    mag_err, snr, separation_arcsec.

    Returns DataFrame sorted by MJD.
    """
    df = pd.read_csv(csv_path)
    required = {"mjd", "band", "flux", "flux_err"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Lightcurve CSV missing columns: {missing}")
    return df.sort_values("mjd").reset_index(drop=True)


def _normalize_flux_per_band(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Subtract per-band mean flux for multi-band period search.

    Normalization allows combining bands with different mean brightnesses
    into a single Lomb-Scargle search. Each band's flux is shifted so its
    mean is zero; errors are unchanged.

    Returns:
        (normalized_flux, flux_err) arrays aligned with df rows.
    """
    norm_flux = np.zeros(len(df))
    flux_err = df["flux_err"].values.copy()

    for band in df["band"].unique():
        mask = df["band"] == band
        band_flux = df.loc[mask, "flux"].values
        band_mean = np.mean(band_flux)
        norm_flux[mask] = band_flux - band_mean

    return norm_flux, flux_err
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestReadLightcurve -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/period.py packages/obs_nickel/tests/test_period.py
git commit -m "feat: add period module with CSV reader and band normalization

New core/period.py module for variable star period analysis.
Reads lightcurve CSVs from extract_lightcurve.py output format,
normalizes flux per band for multi-band Lomb-Scargle search."
```

---

### Task 3: Lomb-Scargle Period Search (Test-First)

Add the core period-finding algorithm.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/period.py`
- Modify: `packages/obs_nickel/tests/test_period.py`

**Step 1: Write the failing test for period search**

Append to `packages/obs_nickel/tests/test_period.py`:

```python
class TestLombScargle:
    """Test Lomb-Scargle period search."""

    def test_finds_correct_period(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _read_lightcurve, _run_lomb_scargle

        csv_path, true_period = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)

        result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )

        # Should find period within 5% of true value
        assert abs(result.best_period - true_period) / true_period < 0.05

    def test_fap_is_low_for_real_signal(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _read_lightcurve, _run_lomb_scargle

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)

        result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )

        # Strong signal should have very low FAP
        assert result.fap < 0.01

    def test_power_spectrum_shape(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import _read_lightcurve, _run_lomb_scargle

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)

        result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )

        assert len(result.periods) == 5000
        assert len(result.powers) == 5000
        assert result.power == np.max(result.powers)

    def test_noise_only_has_high_fap(self, tmp_path):
        """Pure noise should not produce a significant period."""
        from obs_nickel_data_tools.core.period import _read_lightcurve, _run_lomb_scargle

        np.random.seed(99)
        n = 40
        csv_path = tmp_path / "noise.csv"
        import csv

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "mjd", "band", "visit", "ra", "dec",
                "flux", "flux_err", "mag", "mag_err", "snr", "separation_arcsec",
            ])
            for i in range(n):
                mjd = 60000 + i * 1.2
                flux = 1000 + np.random.normal(0, 10)
                writer.writerow([
                    f"{mjd:.6f}", "r", 80000000 + i,
                    "210.0", "54.0",
                    f"{flux:.6f}", "10.0", "20.0", "0.01", "100.0", "0.1",
                ])

        df = _read_lightcurve(csv_path)
        result = _run_lomb_scargle(df, period_min=1.0, period_max=20.0, n_samples=5000)

        # Noise-only: FAP should be high (no significant period)
        assert result.fap > 0.05
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestLombScargle -v`

Expected: FAIL with `ImportError: cannot import name '_run_lomb_scargle'`

**Step 3: Implement Lomb-Scargle search**

Add to `packages/data_tools/src/obs_nickel_data_tools/core/period.py` (after `_normalize_flux_per_band`):

```python
def _run_lomb_scargle(
    df: pd.DataFrame,
    *,
    period_min: float = 0.1,
    period_max: float = 100.0,
    n_samples: int = 10_000,
) -> PeriodResult:
    """Run Lomb-Scargle periodogram on multi-band lightcurve.

    Flux is normalized per band (subtract mean) before combining all bands
    into a single periodogram. This allows joint period detection across
    bands with different mean brightnesses.

    Args:
        df: Lightcurve DataFrame with mjd, band, flux, flux_err columns.
        period_min: Minimum search period in days.
        period_max: Maximum search period in days.
        n_samples: Number of frequency grid points.

    Returns:
        PeriodResult with best period, power spectrum, and FAP.
    """
    from astropy.timeseries import LombScargle

    norm_flux, flux_err = _normalize_flux_per_band(df)
    t = df["mjd"].values

    # Build frequency grid (uniform in frequency, not period)
    freq_min = 1.0 / period_max
    freq_max = 1.0 / period_min
    frequency = np.linspace(freq_min, freq_max, n_samples)

    # Compute Lomb-Scargle periodogram
    ls = LombScargle(t, norm_flux, flux_err)
    power = ls.power(frequency)

    # Find best period
    best_idx = np.argmax(power)
    best_freq = frequency[best_idx]
    best_period = 1.0 / best_freq
    best_power = power[best_idx]

    # False alarm probability (Baluev 2008 analytic method)
    fap = ls.false_alarm_probability(best_power, method="baluev")

    periods = 1.0 / frequency

    return PeriodResult(
        best_period=best_period,
        best_frequency=best_freq,
        power=best_power,
        fap=float(fap),
        periods=periods,
        powers=power,
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestLombScargle -v`

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/period.py packages/obs_nickel/tests/test_period.py
git commit -m "feat: add Lomb-Scargle period search with FAP

Implements multi-band Lomb-Scargle periodogram using
astropy.timeseries.LombScargle with Baluev FAP estimation."
```

---

### Task 4: Phase Folding (Test-First)

Add phase-folding of the lightcurve at the detected period.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/period.py`
- Modify: `packages/obs_nickel/tests/test_period.py`

**Step 1: Write the failing test for phase folding**

Append to `packages/obs_nickel/tests/test_period.py`:

```python
class TestPhaseFolding:
    """Test phase folding at detected period."""

    def test_phase_fold_produces_per_band_data(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import (
            _phase_fold,
            _read_lightcurve,
            _run_lomb_scargle,
        )

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)
        result = _run_lomb_scargle(df, period_min=1.0, period_max=20.0, n_samples=5000)

        phase_data = _phase_fold(df, result.best_period)

        assert "r" in phase_data
        assert "i" in phase_data
        assert "phase" in phase_data["r"]
        assert "flux" in phase_data["r"]
        assert "flux_err" in phase_data["r"]

    def test_phase_values_between_0_and_1(self, sample_lightcurve_csv):
        from obs_nickel_data_tools.core.period import (
            _phase_fold,
            _read_lightcurve,
            _run_lomb_scargle,
        )

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)
        result = _run_lomb_scargle(df, period_min=1.0, period_max=20.0, n_samples=5000)

        phase_data = _phase_fold(df, result.best_period)

        for band_data in phase_data.values():
            phases = band_data["phase"]
            assert np.all(phases >= 0.0)
            assert np.all(phases < 1.0)
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestPhaseFolding -v`

Expected: FAIL with `ImportError: cannot import name '_phase_fold'`

**Step 3: Implement phase folding**

Add to `packages/data_tools/src/obs_nickel_data_tools/core/period.py` (after `_run_lomb_scargle`):

```python
def _phase_fold(
    df: pd.DataFrame, period: float
) -> dict[str, dict[str, np.ndarray]]:
    """Phase-fold lightcurve at given period, per band.

    Args:
        df: Lightcurve DataFrame with mjd, band, flux, flux_err columns.
        period: Folding period in days.

    Returns:
        Dict mapping band name to {phase, flux, flux_err} arrays.
        Phase values are in [0, 1).
    """
    result = {}
    t0 = df["mjd"].min()

    for band in sorted(df["band"].unique()):
        mask = df["band"] == band
        band_df = df[mask]
        phase = ((band_df["mjd"].values - t0) / period) % 1.0
        result[band] = {
            "phase": phase,
            "flux": band_df["flux"].values,
            "flux_err": band_df["flux_err"].values,
        }

    return result
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestPhaseFolding -v`

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/period.py packages/obs_nickel/tests/test_period.py
git commit -m "feat: add phase folding at detected period

Phase-folds multi-band lightcurve per band with phase in [0, 1)."
```

---

### Task 5: Output Generation (Plots + JSON)

Add periodogram plot, phase-folded plot, and JSON result output.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/period.py`
- Modify: `packages/obs_nickel/tests/test_period.py`

**Step 1: Write the failing test for output generation**

Append to `packages/obs_nickel/tests/test_period.py`:

```python
class TestOutputGeneration:
    """Test plot and JSON output files."""

    def test_save_results_creates_json(self, sample_lightcurve_csv, tmp_path):
        from obs_nickel_data_tools.core.period import (
            PeriodResult,
            _phase_fold,
            _read_lightcurve,
            _run_lomb_scargle,
            _save_results,
        )

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)
        ls_result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )
        phase_data = _phase_fold(df, ls_result.best_period)
        ls_result.phase_folded = phase_data

        _save_results(ls_result, tmp_path)

        json_path = tmp_path / "period_results.json"
        assert json_path.exists()

        import json

        with open(json_path) as f:
            data = json.load(f)
        assert "best_period" in data
        assert "fap" in data
        assert "best_frequency" in data

    def test_save_results_creates_periodogram_plot(
        self, sample_lightcurve_csv, tmp_path
    ):
        from obs_nickel_data_tools.core.period import (
            _phase_fold,
            _read_lightcurve,
            _run_lomb_scargle,
            _save_results,
        )

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)
        ls_result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )
        ls_result.phase_folded = _phase_fold(df, ls_result.best_period)

        _save_results(ls_result, tmp_path)

        assert (tmp_path / "periodogram.png").exists()

    def test_save_results_creates_phase_folded_plot(
        self, sample_lightcurve_csv, tmp_path
    ):
        from obs_nickel_data_tools.core.period import (
            _phase_fold,
            _read_lightcurve,
            _run_lomb_scargle,
            _save_results,
        )

        csv_path, _ = sample_lightcurve_csv
        df = _read_lightcurve(csv_path)
        ls_result = _run_lomb_scargle(
            df, period_min=1.0, period_max=20.0, n_samples=5000
        )
        ls_result.phase_folded = _phase_fold(df, ls_result.best_period)

        _save_results(ls_result, tmp_path)

        assert (tmp_path / "phase_folded.png").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestOutputGeneration -v`

Expected: FAIL with `ImportError: cannot import name '_save_results'`

**Step 3: Implement output generation**

Add to `packages/data_tools/src/obs_nickel_data_tools/core/period.py` (after `_phase_fold`):

```python
def _save_results(result: PeriodResult, output_dir: Path) -> None:
    """Save period analysis results: JSON, periodogram plot, phase-folded plot.

    Args:
        result: PeriodResult with power spectrum and phase-folded data.
        output_dir: Directory to write output files.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- JSON results ---
    json_data = {
        "best_period": result.best_period,
        "best_frequency": result.best_frequency,
        "power": result.power,
        "fap": result.fap,
        "n_bands": len(result.phase_folded),
        "bands": list(result.phase_folded.keys()),
    }
    with open(output_dir / "period_results.json", "w") as f:
        json.dump(json_data, f, indent=2)

    # --- Periodogram plot ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(result.periods, result.powers, "k-", linewidth=0.5)
    ax.axvline(result.best_period, color="r", linestyle="--", alpha=0.7,
               label=f"P = {result.best_period:.4f} d")
    ax.set_xlabel("Period (days)")
    ax.set_ylabel("Lomb-Scargle Power")
    ax.set_title(f"Periodogram (FAP = {result.fap:.2e})")
    ax.legend()
    ax.set_xscale("log")
    fig.tight_layout()
    fig.savefig(output_dir / "periodogram.png", dpi=150)
    plt.close(fig)

    # --- Phase-folded plot ---
    band_colors = {"b": "blue", "v": "green", "r": "red", "i": "darkred"}
    fig, ax = plt.subplots(figsize=(8, 5))
    for band, data in sorted(result.phase_folded.items()):
        color = band_colors.get(band, "gray")
        ax.errorbar(
            data["phase"], data["flux"], yerr=data["flux_err"],
            fmt="o", color=color, markersize=4, alpha=0.7,
            label=f"{band}-band",
        )
    ax.set_xlabel("Phase")
    ax.set_ylabel("Flux")
    ax.set_title(f"Phase-folded at P = {result.best_period:.4f} d")
    ax.legend()
    ax.set_xlim(0, 1)
    fig.tight_layout()
    fig.savefig(output_dir / "phase_folded.png", dpi=150)
    plt.close(fig)

    result.output_dir = output_dir
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestOutputGeneration -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/period.py packages/obs_nickel/tests/test_period.py
git commit -m "feat: add period analysis output (plots + JSON)

Generates periodogram.png, phase_folded.png, and period_results.json
with publication-ready styling and machine-readable results."
```

---

### Task 6: Public `run()` Function (Test-First)

Wire everything together into the public `period.run()` entry point.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/period.py`
- Modify: `packages/obs_nickel/tests/test_period.py`

**Step 1: Write the failing test for run()**

Append to `packages/obs_nickel/tests/test_period.py`:

```python
class TestRun:
    """Test the public run() entry point."""

    def test_run_end_to_end(self, sample_lightcurve_csv, tmp_path):
        from obs_nickel_data_tools.core.period import run

        csv_path, true_period = sample_lightcurve_csv
        result = run(
            csv_path,
            period_min=1.0,
            period_max=20.0,
            n_samples=5000,
            output_dir=tmp_path / "period_output",
        )

        # Correct period found
        assert abs(result.best_period - true_period) / true_period < 0.05
        assert result.fap < 0.01

        # All outputs created
        assert (tmp_path / "period_output" / "period_results.json").exists()
        assert (tmp_path / "period_output" / "periodogram.png").exists()
        assert (tmp_path / "period_output" / "phase_folded.png").exists()

        # Phase data populated
        assert "r" in result.phase_folded
        assert "i" in result.phase_folded

    def test_run_with_few_points_does_not_crash(self, tmp_path):
        """Gracefully handle very few data points."""
        from obs_nickel_data_tools.core.period import run

        csv_path = tmp_path / "tiny.csv"
        import csv

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "mjd", "band", "visit", "ra", "dec",
                "flux", "flux_err", "mag", "mag_err", "snr", "separation_arcsec",
            ])
            for i in range(3):
                writer.writerow([
                    f"{60000 + i:.6f}", "r", 80000000 + i,
                    "210.0", "54.0", "1000.0", "10.0", "20.0", "0.01", "100.0", "0.1",
                ])

        result = run(
            csv_path,
            period_min=0.5,
            period_max=10.0,
            n_samples=100,
            output_dir=tmp_path / "tiny_output",
        )

        # Should return a result (even if not scientifically meaningful)
        assert result.best_period > 0
        assert (tmp_path / "tiny_output" / "period_results.json").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_period.py::TestRun -v`

Expected: FAIL (run function not defined or incomplete)

**Step 3: Implement run()**

Add to `packages/data_tools/src/obs_nickel_data_tools/core/period.py` (at the end of file):

```python
def run(
    csv_path: Path,
    *,
    period_min: float = 0.1,
    period_max: float = 100.0,
    n_samples: int = 10_000,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> PeriodResult:
    """Run Lomb-Scargle period search and phase-fold lightcurve.

    This is the main entry point for period analysis. Reads a lightcurve CSV
    (from extract_lightcurve.py), runs a multi-band Lomb-Scargle periodogram,
    phase-folds at the best period, and saves plots + JSON results.

    Args:
        csv_path: Path to lightcurve CSV file.
        period_min: Minimum search period in days (default: 0.1).
        period_max: Maximum search period in days (default: 100.0).
        n_samples: Number of frequency grid points (default: 10,000).
        output_dir: Directory for output files (default: same as CSV).
        log_file: Optional path to write log output.

    Returns:
        PeriodResult with best period, FAP, power spectrum, and phase data.
    """
    if output_dir is None:
        output_dir = csv_path.parent / "period_analysis"

    log.info(f"Reading lightcurve from {csv_path}")
    df = _read_lightcurve(csv_path)
    log.info(
        f"  {len(df)} detections across {df['band'].nunique()} bands, "
        f"spanning {df['mjd'].max() - df['mjd'].min():.1f} days"
    )

    log.info(
        f"Running Lomb-Scargle (P={period_min:.2f}-{period_max:.2f} d, "
        f"{n_samples} samples)"
    )
    result = _run_lomb_scargle(
        df, period_min=period_min, period_max=period_max, n_samples=n_samples
    )

    log.info(f"  Best period: {result.best_period:.6f} d (FAP={result.fap:.2e})")

    log.info("Phase-folding lightcurve")
    result.phase_folded = _phase_fold(df, result.best_period)

    log.info(f"Saving results to {output_dir}")
    _save_results(result, output_dir)

    return result
```

**Step 4: Run all period tests**

Run: `pytest packages/obs_nickel/tests/test_period.py -v`

Expected: All 12 tests PASS

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/period.py packages/obs_nickel/tests/test_period.py
git commit -m "feat: add period.run() public entry point

Wires together CSV reading, Lomb-Scargle search, phase folding,
and output generation into a single run() function callable from
the pipeline orchestrator."
```

---

### Task 7: RunConfig Extension (Test-First)

Add `pipeline_type` and `period_*` fields to RunConfig, with smart defaults.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py` (lines 337-462)
- Create: `packages/obs_nickel/tests/test_run_config.py`

**Step 1: Write the failing test for new RunConfig fields**

Write `packages/obs_nickel/tests/test_run_config.py`:

```python
"""Tests for RunConfig variable star extensions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "data_tools/src"),
)


@pytest.fixture
def sn_yaml(tmp_path):
    """Minimal supernova YAML config (existing behavior)."""
    cfg = {
        "object": "2023ixf",
        "ra": 210.91,
        "dec": 54.32,
        "bands": ["r", "i"],
        "science": {"nights": [20230519]},
        "options": {"jobs": 4},
    }
    path = tmp_path / "sn.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


@pytest.fixture
def variable_yaml(tmp_path):
    """Variable star YAML config with period search enabled."""
    cfg = {
        "object": "V0678-Oph",
        "ra": 257.123,
        "dec": -18.456,
        "bands": ["b", "v", "r", "i"],
        "template": {"type": "coadd", "nights": [20230601, 20230615]},
        "science": {"nights": [20230701]},
        "options": {
            "pipeline_type": "variable",
            "period_search": True,
            "period_min": 0.5,
            "period_max": 50.0,
            "period_samples": 8000,
            "forced_phot_image_type": "both",
        },
    }
    path = tmp_path / "variable.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


@pytest.fixture
def variable_defaults_yaml(tmp_path):
    """Variable config relying on pipeline_type defaults."""
    cfg = {
        "object": "RR-Lyr",
        "ra": 286.0,
        "dec": 42.0,
        "bands": ["r"],
        "science": {"nights": [20230801]},
        "options": {
            "pipeline_type": "variable",
        },
    }
    path = tmp_path / "var_defaults.yaml"
    with open(path, "w") as f:
        yaml.dump(cfg, f)
    return path


class TestRunConfigNewFields:
    """Test new variable star fields in RunConfig."""

    def test_sn_config_has_defaults(self, sn_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(sn_yaml)

        assert cfg.pipeline_type == "supernova"
        assert cfg.period_search is False
        assert cfg.period_min == 0.1
        assert cfg.period_max == 100.0
        assert cfg.period_samples == 10_000
        # SN default: diffim only
        assert cfg.forced_phot_image_type == "diffim"

    def test_variable_config_parses_all_fields(self, variable_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(variable_yaml)

        assert cfg.pipeline_type == "variable"
        assert cfg.period_search is True
        assert cfg.period_min == 0.5
        assert cfg.period_max == 50.0
        assert cfg.period_samples == 8000
        assert cfg.forced_phot_image_type == "both"

    def test_variable_type_defaults_forced_phot_to_both(self, variable_defaults_yaml):
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = RunConfig.from_yaml(variable_defaults_yaml)

        assert cfg.pipeline_type == "variable"
        # pipeline_type=variable should default forced_phot_image_type to "both"
        assert cfg.forced_phot_image_type == "both"

    def test_explicit_forced_phot_overrides_variable_default(self, tmp_path):
        """User explicitly sets diffim even with pipeline_type=variable."""
        from obs_nickel_data_tools.core.run import RunConfig

        cfg = {
            "object": "test",
            "ra": 100.0,
            "dec": 10.0,
            "bands": ["r"],
            "science": {"nights": [20230101]},
            "options": {
                "pipeline_type": "variable",
                "forced_phot_image_type": "diffim",
            },
        }
        path = tmp_path / "override.yaml"
        with open(path, "w") as f:
            yaml.dump(cfg, f)

        rc = RunConfig.from_yaml(path)
        assert rc.forced_phot_image_type == "diffim"
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/obs_nickel/tests/test_run_config.py -v`

Expected: FAIL (missing `pipeline_type` attribute or incorrect defaults)

**Step 3: Modify RunConfig dataclass**

In `packages/data_tools/src/obs_nickel_data_tools/core/run.py`, add new fields to the `RunConfig` dataclass after line 370 (`use_fallbacks: bool = True`):

```python
    # Variable star options
    pipeline_type: str = "supernova"  # "supernova" or "variable"
    period_search: bool = False
    period_min: float = 0.1
    period_max: float = 100.0
    period_samples: int = 10_000
```

Then modify `from_yaml()` — in the `return cls(...)` block (around line 434-462), add the new fields and apply `pipeline_type` defaults. Replace the `forced_phot_image_type` line and add period fields:

```python
        # Apply pipeline_type defaults before explicit overrides
        pipeline_type = options.get("pipeline_type", "supernova")

        # Variable star default: forced phot on both visit + diffim
        if pipeline_type == "variable" and "forced_phot_image_type" not in options:
            default_fphot_type = "both"
        else:
            default_fphot_type = "diffim"

        return cls(
            # ... existing fields unchanged ...
            forced_phot_image_type=options.get("forced_phot_image_type", default_fphot_type),
            # ... rest of existing fields ...
            pipeline_type=pipeline_type,
            period_search=options.get("period_search", False),
            period_min=float(options.get("period_min", 0.1)),
            period_max=float(options.get("period_max", 100.0)),
            period_samples=int(options.get("period_samples", 10_000)),
        )
```

**Important:** The `forced_phot_image_type` line at ~452 changes from:
```python
forced_phot_image_type=options.get("forced_phot_image_type", "diffim"),
```
to:
```python
forced_phot_image_type=options.get("forced_phot_image_type", default_fphot_type),
```

And add the `pipeline_type` / `default_fphot_type` logic before the `return cls(...)` call.

**Step 4: Run test to verify it passes**

Run: `pytest packages/obs_nickel/tests/test_run_config.py -v`

Expected: All 4 tests PASS

**Step 5: Also run existing tests to ensure no regression**

Run: `pytest packages/obs_nickel/tests/ -v`

Expected: All existing tests still PASS

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py packages/obs_nickel/tests/test_run_config.py
git commit -m "feat: add pipeline_type and period_search to RunConfig

Extends YAML config with pipeline_type (supernova/variable) and
period search parameters. Variable type defaults forced_phot_image_type
to 'both' unless explicitly overridden."
```

---

### Task 8: Orchestrator Period Step + RunResult + Summary

Wire the period analysis step into the pipeline orchestrator.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py` (RunResult, _run_period_step, run() function, summary)

**Step 1: Add `period_result_path` to RunResult**

In `packages/data_tools/src/obs_nickel_data_tools/core/run.py`, modify `RunResult` (line ~503-516):

Add after `lightcurve_path`:
```python
    period_result_path: str | None = None
```

**Step 2: Add `_run_period_step` function**

Add after the `_run_lightcurve_step` function (before the `_gather_*` helper functions or before `run()`):

```python
def _run_period_step(
    run_cfg: RunConfig,
    result: RunResult,
    dry_run: bool,
) -> None:
    """Run period analysis on extracted lightcurve.

    Executes Lomb-Scargle period search and phase folding on the
    lightcurve CSV produced by the previous lightcurve extraction step.
    Only runs if period_search is enabled and a lightcurve was produced.
    """
    if not result.lightcurve_path:
        log.warning("No lightcurve available, skipping period search")
        return

    if not dry_run:
        from obs_nickel_data_tools.core import period

        period_log = _get_step_log_file("period")
        period_result = period.run(
            csv_path=Path(result.lightcurve_path),
            period_min=run_cfg.period_min,
            period_max=run_cfg.period_max,
            n_samples=run_cfg.period_samples,
            output_dir=Path(result.lightcurve_path).parent / "period_analysis",
            log_file=period_log,
        )
        result.period_result_path = str(period_result.output_dir)
        log.info(
            f"  Best period: {period_result.best_period:.6f} d "
            f"(FAP={period_result.fap:.2e})"
        )
    else:
        log.info("  [DRY RUN] period.run()")
```

**Step 3: Insert period step into `run()` function**

In the `run()` function, after the lightcurve step (line ~1224) and before the summary section (line ~1226), add:

```python
    # Step 7: Period analysis (variable stars only)
    if run_cfg.period_search:
        log.info("Running period analysis...")
        _run_period_step(run_cfg, result, dry_run)
```

**Step 4: Update summary output**

In the summary section of `run()`, after the lightcurve log line (line ~1300), add:

```python
    if result.period_result_path:
        log.info(f"  Period analysis: {result.period_result_path}")
```

And in the summary.txt writer (after line ~1323), add:

```python
        if result.period_result_path:
            f.write(f"Period analysis: {result.period_result_path}\n")
```

**Step 5: Update `has_successes` check**

In the three-tier status section (line ~1253), extend the success check:

```python
        has_successes = (
            successful_science > 0
            or successful_dia_pairs > 0
            or successful_fphot > 0
            or result.lightcurve_path is not None
            or result.period_result_path is not None
        )
```

**Step 6: Run existing tests**

Run: `pytest packages/obs_nickel/tests/ -v`

Expected: All tests PASS

**Step 7: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "feat: wire period analysis step into pipeline orchestrator

Adds Step 7 (period search) after lightcurve extraction in the run()
function. Only executes when period_search=true in config. Updates
RunResult, summary output, and dry-run support."
```

---

### Task 9: Update Docstring and Module Header

Update the `run.py` module docstring to document the new YAML options and pipeline step.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py` (lines 1-58, 1111-1121)

**Step 1: Update module docstring**

In the module docstring (line 1-58), update the YAML example and pipeline description.

Add to the example YAML `options:` section (after `use_fallbacks: true`, around line 57):

```python
      pipeline_type: supernova   # or "variable" for variable star campaigns
      period_search: false       # Enable Lomb-Scargle period search
      period_min: 0.1            # Minimum search period (days)
      period_max: 100.0          # Maximum search period (days)
      period_samples: 10000      # Frequency grid density
```

Update the pipeline description (line 4) from:
```
calibs → science → DIA → forced photometry → lightcurve.
```
to:
```
calibs → science → DIA → forced photometry → lightcurve → period analysis.
```

Update the `run()` docstring (around line 1111-1121) to add step 7:

```python
    """Run full pipeline from YAML configuration.

    This orchestrates:
    0. Bootstrap repository if needed (auto-detected)
    1. PS1 template ingestion (or coadd building) per band
    2. Calibrations per night
    3. Science processing per night
    4. DIA per night per band
    5. Forced photometry per night
    6. Lightcurve extraction
    7. Period analysis (variable stars, if period_search=true)
```

**Step 2: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "docs: update run.py docstrings for variable star support

Documents new pipeline_type, period_search YAML options and
Step 7 period analysis in module and function docstrings."
```

---

### Task 10: Example Variable Star Campaign Config

Create an example YAML config that shows how to set up a variable star campaign.

**Files:**
- Create: `scripts/config/example_variable_star/pipeline_variable_template.yaml`

**Step 1: Create example config**

Write `scripts/config/example_variable_star/pipeline_variable_template.yaml`:

```yaml
# Example pipeline configuration for a variable star campaign
#
# Usage:
#   nickel run scripts/config/example_variable_star/pipeline_variable_template.yaml
#   nickel run scripts/config/example_variable_star/pipeline_variable_template.yaml --dry-run
#
# This is a TEMPLATE - copy and customize for your target:
#   1. Replace object/ra/dec with your variable star coordinates
#   2. Set template nights spanning multiple variability cycles
#   3. Set science nights for your observing campaign
#   4. Adjust period_min/period_max to your expected range
#   5. Update env paths to match your system
#
# Pipeline steps:
#   0. Bootstrap repository (automatic if needed)
#   1. Build coadd templates from many epochs (median → mean flux reference)
#   2. Run calibrations per night
#   3. Run science processing per night
#   4. Run DIA per night per band (measures deviation from mean flux)
#   5. Run forced photometry at variable star coordinates (visit + diffim)
#   6. Extract combined multi-band lightcurve
#   7. Run Lomb-Scargle period search and phase folding

# =============================================================================
# Environment Configuration (update paths for your system)
# =============================================================================
env:
  REPO: "/path/to/butler/repo"
  STACK_DIR: "/path/to/lsst_stack"
  OBS_NICKEL: "/path/to/nickel_processing_suite/packages/obs_nickel"
  RAW_PARENT_DIR: "/path/to/raw/data"
  REFCAT_REPO: "/path/to/refcats"

# Target information
# Replace with your variable star coordinates
object: "V0678-Oph"
ra: 257.123
dec: -18.456

# Bands to process (Nickel supports b, v, r, i)
bands: ["b", "v", "r", "i"]

# Template configuration - use Nickel coadds from many epochs
# Choose nights spanning multiple variability cycles so the median
# stack approximates the star's mean brightness.
template:
  type: coadd
  nights:
    - 20230601
    - 20230615
    - 20230620
    - 20230701
    - 20230715
    - 20230801

# Science nights - your observing campaign
science:
  nights:
    - 20230701
    - 20230705
    - 20230710
    - 20230715
    - 20230720

# Pipeline configuration files (paths relative to obs_nickel/configs/)
configs:
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/dense_relaxed.py
      - calibrateImage/tuned_configs/sparse_strict.py
      - calibrateImage/tuned_configs/sparse_relaxed.py
    colorterms: apply_colorterms.py
  coadd:
    make_direct_warp: coadds/makeDirectWarp_relaxed.py
  dia:
    subtract_images: dia/subtractImages.py
    # Use sensitive detection for variable star source catalogs (optional)
    # Standard detectAndMeasure.py (3.0 sigma) also works fine since
    # forced photometry at known coordinates is threshold-independent.
    detect_and_measure: dia/detectAndMeasure_sensitive.py

# Processing options
options:
  jobs: 6
  skip_calibs: false
  skip_science: false
  rebuild_templates: false
  skip_dia: false
  continue_on_error: true
  use_fallbacks: true

  # Variable star specific options
  pipeline_type: variable
  forced_phot: true
  forced_phot_image_type: both    # Measure on both visit images AND difference images
  lightcurve: true
  lightcurve_dataset_type: forced_phot_diffim_radec
  lightcurve_min_snr: 0           # Keep all detections for period search

  # Period search configuration
  period_search: true
  period_min: 0.1                 # Minimum search period (days)
  period_max: 100.0               # Maximum search period (days)
  period_samples: 10000           # Frequency grid resolution
```

**Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('scripts/config/example_variable_star/pipeline_variable_template.yaml')); print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/config/example_variable_star/pipeline_variable_template.yaml
git commit -m "feat: add example variable star campaign YAML config

Template config demonstrating pipeline_type=variable with period
search, coadd templates, and multi-band forced photometry."
```

---

### Task 11: Run Full Test Suite

Verify everything works together.

**Step 1: Run all tests**

Run: `pytest packages/obs_nickel/tests/ -v`

Expected: All tests PASS (existing + new)

**Step 2: Run linter**

Run: `ruff check packages/data_tools/src/obs_nickel_data_tools/core/period.py`

Expected: No errors

**Step 3: Verify dry run parses variable config**

Run: `python -c "
import sys; sys.path.insert(0, 'packages/data_tools/src')
from pathlib import Path
from obs_nickel_data_tools.core.run import RunConfig
cfg = RunConfig.from_yaml(Path('scripts/config/example_variable_star/pipeline_variable_template.yaml'))
print(f'pipeline_type={cfg.pipeline_type}')
print(f'period_search={cfg.period_search}')
print(f'period_min={cfg.period_min}')
print(f'period_max={cfg.period_max}')
print(f'forced_phot_image_type={cfg.forced_phot_image_type}')
"`

Expected:
```
pipeline_type=variable
period_search=True
period_min=0.1
period_max=100.0
forced_phot_image_type=both
```

---

## Summary

| Task | Description | New/Modified Files |
|------|------------|-------------------|
| 1 | Sensitive DIA detection config | `configs/dia/detectAndMeasure_sensitive.py` (new) |
| 2 | PeriodResult + CSV reader | `core/period.py` (new), `tests/test_period.py` (new) |
| 3 | Lomb-Scargle search | `core/period.py`, `tests/test_period.py` |
| 4 | Phase folding | `core/period.py`, `tests/test_period.py` |
| 5 | Output generation | `core/period.py`, `tests/test_period.py` |
| 6 | Public run() | `core/period.py`, `tests/test_period.py` |
| 7 | RunConfig extension | `core/run.py`, `tests/test_run_config.py` (new) |
| 8 | Orchestrator period step | `core/run.py` |
| 9 | Docstring updates | `core/run.py` |
| 10 | Example config | `scripts/config/example_variable_star/` (new) |
| 11 | Full test suite | (verification only) |
