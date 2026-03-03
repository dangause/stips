# LSST-Native Differential Photometry Task

## Problem

PSF-fitting forced photometry fails catastrophically on bright stars (82.9% scatter for HD 189733, B=8.6). A standalone `differential_phot.py` script was built as a workaround, but it bypasses Butler and the LSST pipeline framework entirely, reading raw FITS pixels.

The LSST `calibrateImage` task already computes aperture fluxes at 9 radii (3-70 px) for every detected source in `initial_stars_detector` catalogs. We should use this existing data rather than re-measuring pixels.

## Approach

Build a single consolidation-level `PipelineTask` that reads `initial_stars_detector` catalogs from all visits, selects a comparison star ensemble, and computes differential flux ratios. No new pixel-level measurement needed.

## Architecture

### Data Flow

```
calibrateImage (per visit)
    |
    v
initial_stars_detector (SourceCatalog, per visit/detector)
    |
    v
DifferentialPhotTask (instrument-level consolidation)
    1. Load all initial_stars_detector catalogs
    2. Pick reference visit, select comparison stars
    3. Cross-match target + comparisons across all visits
    4. Extract aperture flux at configured radius
    5. Compute differential flux ratio per visit
    6. Normalize time series
    |
    v
differential_phot_lightcurve (ArrowAstropy, instrument-level)
```

### Why Instrumental Flux

`initial_stars_detector` contains pre-PhotoCalib instrumental fluxes. In the ratio `target / sum(comparisons)`, the photometric zero-point cancels exactly. This avoids propagating calibration noise from the (often noisy) Nickel PhotoCalib fits.

### Task Pattern

Follows the `ForcedPhotLightcurveTask` consolidation pattern:
- Dimensions: `(instrument,)` -- runs once per instrument
- Inputs: `multiple=True`, `deferLoad=True` for per-visit catalogs
- Output: single Astropy table with the differential lightcurve

## Pipeline Connections

```python
class DifferentialPhotConnections(
    PipelineTaskConnections,
    dimensions=("instrument",),
):
    starCatalogs = ct.Input(
        name="initial_stars_detector",
        storageClass="SourceCatalog",
        dimensions=("instrument", "visit", "detector"),
        multiple=True,
        deferLoad=True,
    )

    visitTable = ct.Input(
        name="preliminary_visit_table",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )

    lightcurve = ct.Output(
        name="differential_phot_lightcurve",
        storageClass="ArrowAstropy",
        dimensions=("instrument",),
    )
```

## Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `targetRa` | float | required | Target RA in degrees |
| `targetDec` | float | required | Target Dec in degrees |
| `apertureRadius` | float | 17.0 | Aperture radius in pixels (must match a calibrateImage radius) |
| `nComparisons` | int | 10 | Max number of comparison stars |
| `minComparisons` | int | 3 | Minimum comparisons before skipping a visit |
| `matchRadius` | float | 2.0 | Cross-match tolerance in arcsec |
| `minRelMag` | float | 0.5 | Min magnitude fainter than target for comparisons |
| `maxRelMag` | float | 4.0 | Max magnitude fainter than target for comparisons |
| `minDetectionFraction` | float | 0.8 | Minimum fraction of visits a comparison must appear in |
| `bandFilter` | str | "" | Only process this band (empty = all bands) |

## Comparison Star Selection Algorithm

### Step 1: Pick Reference Visit

Choose the visit with the most detected sources (proxy for best seeing/conditions). Load its `initial_stars_detector` catalog.

### Step 2: Identify Target

Cross-match `(targetRa, targetDec)` against catalog `coord_ra`/`coord_dec` within `matchRadius`. If no match, fall back to next-best reference visit.

### Step 3: Select Candidates

From the reference visit catalog, filter comparison candidates by:
- Brightness: within `minRelMag` to `maxRelMag` of target's aperture flux
- Flags: exclude saturated, edge, bad pixel flags
- Isolation: `deblend_nChild == 0` (not deblended)

Sort by brightness (brightest first, higher SNR).

### Step 4: Verify Stability

For each candidate, cross-match across all visits:
- Keep only stars detected in >= `minDetectionFraction` of visits
- Compute RMS of aperture flux across visits
- Rank by RMS (lower = more stable)
- Select top `nComparisons`

### Step 5: Per-Visit Differential Flux

For each visit:
1. Look up target aperture flux
2. Look up all comparison star aperture fluxes (cross-match by position)
3. `diff_flux = target_flux / sum(comparison_fluxes)`
4. Propagate errors: `diff_err = target_err / comp_sum`
5. If fewer than `minComparisons` found: skip this visit

### Step 6: Normalize

`norm_flux = diff_flux / median(diff_flux)` across all visits.

## Output Columns

| Column | Type | Description |
|--------|------|-------------|
| `mjd` | float | Mid-exposure MJD (from preliminary_visit_table) |
| `band` | str | Filter band |
| `visit` | int | Visit ID |
| `norm_flux` | float | Normalized differential flux (median = 1.0) |
| `norm_flux_err` | float | Error on normalized flux |
| `target_flux` | float | Raw target aperture flux (instrumental) |
| `comp_sum` | float | Sum of comparison star fluxes |
| `n_comps` | int | Number of comparison stars used this visit |
| `airmass` | float | Airmass (from visit table) |
| `aperture_radius_px` | float | Aperture radius used |

## File Structure

### New Files

```
packages/obs_nickel/python/lsst/obs/nickel/tasks/
    differentialPhot.py              # Task + Config + Connections

packages/obs_nickel/pipelines/
    DifferentialPhot.yaml            # Pipeline definition

packages/obs_nickel/configs/
    differentialPhot/
        default.py                   # Default config overrides
```

### Modified Files

```
packages/obs_nickel/python/lsst/obs/nickel/tasks/__init__.py
    -- Add DifferentialPhotTask, DifferentialPhotConfig imports

packages/data_tools/src/obs_nickel_data_tools/core/run.py
    -- Replace _run_differential_phot_step() to invoke LSST pipeline

packages/obs_nickel/tests/
    test_differential_phot.py        # Unit tests for the task
```

### Deprecated (remove after validation)

```
packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/differential_phot.py
```

## Pipeline YAML

```yaml
# DifferentialPhot.yaml
instrument: lsst.obs.nickel.Nickel

tasks:
  differentialPhot:
    class: lsst.obs.nickel.tasks.DifferentialPhotTask
    config:
      connections.starCatalogs: initial_stars_detector
      connections.visitTable: preliminary_visit_table
      connections.lightcurve: differential_phot_lightcurve
      apertureRadius: 17.0
      nComparisons: 10
```

## Integration with `nickel run`

The `run.py` orchestrator replaces the current `_run_differential_phot_step()` (which calls the standalone script) with a `pipetask run` invocation:

```
pipetask run -p $OBS_NICKEL/pipelines/DifferentialPhot.yaml \
    -i {science_collection},{calib_collection} \
    -o {diffphot_output_collection} \
    -c differentialPhot:targetRa={ra} \
    -c differentialPhot:targetDec={dec} \
    -c differentialPhot:apertureRadius={radius} \
    -c differentialPhot:bandFilter={band}
```

Config overrides for target coordinates come from the YAML pipeline config, same as forced photometry today.

## Testing

1. Unit tests for comparison star selection (mock catalogs with known stars)
2. Unit tests for differential flux computation (synthetic lightcurve with injected transit/variable signal)
3. Integration test with HD 189733 b data (expect ~5% dip detection)
4. Integration test with variable star data (expect period recovery matching previous results)

## Use Cases

- **Exoplanet transits**: HD 189733 b B-band transit detection (validated: 13-sigma with standalone script)
- **Variable stars**: CY Aqr, DY Peg, AC And pulsation monitoring (replaces PSF forced photometry)
- **Any bright star time-domain science** on the Nickel telescope

## Risks

- `initial_stars_detector` may use different aperture columns across LSST stack versions
- Cross-matching assumes stable WCS across visits (verified for Nickel)
- Very bright stars (B < 7) may saturate and not appear in catalogs
- SourceCatalog → Astropy Table conversion adds overhead (mitigated by deferLoad)
