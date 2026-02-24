# Variable Star Pipeline Extension Design

**Date:** 2026-02-19
**Status:** Approved
**Approach:** Minimal Config Extension (~320 lines across 4 files)

## Motivation

The Nickel Processing Suite currently processes supernova monitoring campaigns using LSST Science Pipelines difference imaging analysis. The goal is to extend the pipeline to also support known variable star science with period analysis, requiring minimal code changes while maintaining scientific legitimacy.

The pipeline is already ~85-90% variable-star compatible. The architecture is position-based (RA/Dec), band-agnostic, and modular. The primary SN-specific elements are conceptual/configuration rather than code-level barriers.

## Science Case

- **Single known variable star per pipeline run** (same single-target RA/Dec model as SNe)
- **Coadd many-epoch templates** using median stacking to approximate mean flux
- **Lomb-Scargle period search** with false alarm probability assessment
- **Phase folding** of multi-band lightcurves at detected period
- **Forced photometry on both visit AND difference images** (total flux + differential flux)

### Why DIA Works for Variables

Variable stars ARE present in coadd templates (unlike SNe which are absent). Median stacking across many epochs spanning multiple variability cycles produces a template representing the star's mean flux. DIA then measures the deviation from this mean at each epoch: positive flux when brighter than average, negative when fainter. This is the standard approach used by ZTF, OGLE, and LSST for variable star surveys.

### Template Strategy

Existing coadd template infrastructure works unchanged:
- Use many template nights spanning multiple variability cycles
- Median stacking (LSST default `statisticsCoadd`) approximates mean flux
- Degenerate WCS filtering in `coadd.py:find_degenerate_wcs_visits()` applies normally

## Design

### 1. YAML Config Extension

New fields in the `options:` section of pipeline YAML configs:

```yaml
# Existing fields unchanged
object: "V0678-Oph"
ra: 257.123
dec: -18.456
bands: ["b", "v", "r", "i"]

template:
  type: coadd
  nights: [20230601, 20230615, 20230620, 20230701, 20230715]

options:
  # Existing options all retained with current defaults
  forced_phot: true
  forced_phot_image_type: both        # "both" for variables (visit + diffim)
  lightcurve: true
  lightcurve_dataset_type: forced_phot_diffim_radec
  lightcurve_min_snr: 0               # Keep all detections for period search

  # New variable star options
  pipeline_type: variable             # "supernova" (default) or "variable"
  period_search: true                 # Enable Lomb-Scargle after lightcurve
  period_min: 0.1                     # Minimum search period (days)
  period_max: 100.0                   # Maximum search period (days)
  period_samples: 10000               # Frequency grid density

  # Optional: sensitive DIA detection (for blind source catalog)
  dia:
    detect_and_measure: dia/detectAndMeasure_sensitive.py
```

**`pipeline_type`** controls behavioral defaults:
- `"supernova"` (default): current behavior, no changes
- `"variable"`: sets `forced_phot_image_type` default to `"both"`, enables period analysis step

### 2. New Module: `core/period.py` (~200 lines)

Self-contained period analysis module using `astropy.timeseries.LombScargle`.

```python
"""Period search and phase folding for variable star lightcurves."""

@dataclass
class PeriodResult:
    best_period: float          # days
    best_frequency: float       # 1/days
    power: float                # Lomb-Scargle power at best period
    fap: float                  # False alarm probability (Baluev method)
    periods: np.ndarray         # Full period grid
    powers: np.ndarray          # Full power spectrum
    phase_folded: dict          # {band: {phase, flux, flux_err}} per band
    output_dir: Path            # Where plots/data were saved

def run(
    csv_path: Path,             # Lightcurve CSV from extract_lightcurve
    *,
    period_min: float = 0.1,
    period_max: float = 100.0,
    n_samples: int = 10_000,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> PeriodResult:
    """Run Lomb-Scargle period search and phase-fold lightcurve."""
```

**Implementation details:**
- Reads lightcurve CSV produced by `extract_lightcurve.py` (columns: `mjd`, `band`, `flux`, `flux_err`)
- Runs Lomb-Scargle on combined multi-band data (flux normalized per band)
- Reports best period, FAP via Baluev method, and power spectrum
- Phase-folds lightcurve at best period, per band
- Produces three output files:
  - `periodogram.png` - Power vs period with FAP threshold lines
  - `phase_folded.png` - Phase-folded lightcurve, color-coded by band
  - `period_results.json` - Machine-readable results (period, FAP, etc.)

**Dependencies:** `astropy.timeseries.LombScargle` (already in LSST stack), `numpy`, `matplotlib`

### 3. Orchestrator Changes: `core/run.py` (~55 lines modified)

**RunConfig dataclass additions** (~15 lines):

```python
# New fields in RunConfig
pipeline_type: str = "supernova"      # "supernova" or "variable"
period_search: bool = False
period_min: float = 0.1
period_max: float = 100.0
period_samples: int = 10_000
```

**RunConfig.from_yaml() parsing** (~10 lines):
- Parse new fields from `options:` section
- Apply `pipeline_type` defaults (e.g., `"variable"` sets `forced_phot_image_type` to `"both"` unless explicitly overridden)

**RunResult extension** (~5 lines):
- Add `period_result_path: str | None = None` field

**New step function** (~25 lines):

```python
def _run_period_step(run_cfg, result, dry_run):
    """Run period analysis on extracted lightcurve."""
    from obs_nickel_data_tools.core import period

    if not result.lightcurve_path:
        log.warning("No lightcurve available, skipping period search")
        return

    if not dry_run:
        period_log = _get_step_log_file("period")
        period_result = period.run(
            csv_path=Path(result.lightcurve_path),
            period_min=run_cfg.period_min,
            period_max=run_cfg.period_max,
            n_samples=run_cfg.period_samples,
            output_dir=Path(result.lightcurve_path).parent,
            log_file=period_log,
        )
        result.period_result_path = str(period_result.output_dir)
        log.info(f"  Best period: {period_result.best_period:.6f} d "
                 f"(FAP={period_result.fap:.2e})")
```

**Pipeline step insertion** (after Step 6: Lightcurve, before summary):

```python
# Step 7: Period analysis (variable stars only)
if run_cfg.period_search and run_cfg.lightcurve:
    log.info("Running period analysis...")
    _run_period_step(run_cfg, result, dry_run)
```

### 4. Sensitive DIA Detection Config (New File)

`packages/obs_nickel/configs/dia/detectAndMeasure_sensitive.py` (~10 lines):

```python
# ruff: noqa: F821
"""Sensitive detection for low-amplitude variable star DIA sources."""

# Import base config (reuse residual checks)
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0

# Lower detection threshold for subtle variability
if hasattr(config, "detection"):
    config.detection.thresholdValue = 1.5  # sigma (vs 3.0 for SNe)
    config.detection.thresholdType = "stdev"
    config.detection.minPixels = 3         # smaller footprints (vs 5)

if hasattr(config, "doSkySources"):
    config.doSkySources = True
if hasattr(config, "doMeasurement"):
    config.doMeasurement = True
if hasattr(config, "doWriteSubtractedExp"):
    config.doWriteSubtractedExp = True
```

**Note:** This config is optional. For forced photometry at known RA/Dec (the primary use case), the detection threshold doesn't affect results since forced phot measures at the specified position regardless. The sensitive config is only useful for blind DIA source catalog detection.

## What Does NOT Change

The following modules, pipelines, and configs remain completely untouched:

| Component | Why No Changes Needed |
|-----------|----------------------|
| `core/calibs.py` | Calibration is target-agnostic |
| `core/science.py` | ISR/WCS/photometry works for any point source |
| `core/coadd.py` | Median stacking already produces mean-flux templates |
| `core/dia.py` | DIA measures flux deviations from template mean (works for variables) |
| `core/fphot.py` | Forced phot at RA/Dec is target-type agnostic |
| `core/lightcurve.py` | Already handles negative fluxes, multi-band, configurable SNR |
| `core/pipeline.py` | Shared utilities are generic |
| `core/stack.py` | LSST wrappers are generic |
| `core/bootstrap.py` | Repo initialization is target-agnostic |
| `cli.py` | No new CLI commands needed; `nickel run` handles everything |
| `pipelines/DRP.yaml` | Pipeline definitions are target-agnostic |
| `pipelines/DIA.yaml` | Detection config is overridden via config files |
| `pipelines/ForcedPhotRaDec.yaml` | Already supports visit + diffim forced phot |
| All existing YAML configs | SN campaigns continue working unchanged |

### DIA `diff_count == 0` Check

The `dia.py` check at lines ~395-415 that fails when `diff_count == 0` is NOT a variable-star incompatibility. It detects template spatial overlap failure (rewarpTemplate found no template pixels overlapping the science visit footprint). Variable stars produce non-zero difference counts because the template covers the same field. This check works correctly for both SNe and variables.

## Complete Change Summary

| File | Change Type | Lines | Description |
|------|------------|-------|-------------|
| `core/period.py` | **New** | ~200 | Lomb-Scargle + phase folding module |
| `core/run.py` | Modified | ~55 | RunConfig fields, from_yaml parsing, period step |
| `configs/dia/detectAndMeasure_sensitive.py` | **New** | ~10 | Optional 1.5sigma detection |
| Variable star YAML config | **New** | ~50 | Example campaign config |
| **Total** | | **~315** | |

## Usage Example

```bash
# Create variable star config (based on existing SN template)
cp scripts/config/2023ixf/pipeline_nickel_template.yaml \
   scripts/config/v0678oph/pipeline_nickel_template.yaml

# Edit: change object/ra/dec/bands, set pipeline_type: variable,
#        set period_search: true, adjust template nights

# Run the full pipeline
nickel run scripts/config/v0678oph/pipeline_nickel_template.yaml
```

The pipeline executes: calibs -> science -> coadd templates -> DIA -> forced phot (visit + diffim) -> lightcurve -> **period search** -> summary.

## Scientific References

- **Lomb-Scargle periodogram:** Lomb (1976), Scargle (1982); implementation via `astropy.timeseries.LombScargle`
- **False alarm probability:** Baluev (2008) analytic method
- **DIA for variables:** Alard & Lupton (1998) image subtraction; used by ZTF, OGLE, LSST for variable star surveys
- **Mean-flux templates:** Median stacking across multiple cycles produces reference frame at approximately mean brightness
