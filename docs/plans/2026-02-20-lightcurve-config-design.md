# Lightcurve Configuration System Design

**Date:** 2026-02-20
**Status:** Approved

## Summary

Add a dedicated `lightcurve:` top-level section to pipeline YAML configs, backed by a `LightcurveConfig` dataclass. This gives users control over data selection (flux source, S/N threshold, dataset type) and display (y-axis mode, x-axis mode) in a single place. Both the YAML orchestrator (`nickel run`) and standalone CLI (`nickel lightcurve`) support the full config.

## YAML Config Schema

New `lightcurve:` top-level section in pipeline YAML configs:

```yaml
lightcurve:
  enabled: true                            # bool, default true

  # --- Data selection ---
  dataset_type: forced_phot_diffim_radec   # "forced_phot_diffim_radec" | "dia_source_unfiltered"
  min_snr: 0                               # float, default 3.0
  radius: 1.0                              # float (arcsec), default 1.0
  band: null                               # null (all) | "r" | "i" | etc.

  # --- Y-axis ---
  y_axis: apparent_mag                     # "apparent_mag" | "absolute_mag" | "flux_nJy" | "flux_adu"
  distance_modulus: null                   # float, required when y_axis = absolute_mag

  # --- X-axis ---
  x_axis: mjd                             # "mjd" | "days_since_explosion"
  explosion_mjd: null                      # float, required when x_axis = days_since_explosion
```

**Backwards compatibility:** The old `options:` keys (`lightcurve`, `lightcurve_dataset_type`, `lightcurve_min_snr`) still work. If both exist, `lightcurve:` section takes precedence.

**Validation rules:**
- `y_axis: absolute_mag` requires `distance_modulus` to be set
- `x_axis: days_since_explosion` requires `explosion_mjd` to be set
- Validation errors raised at config parse time with clear messages

## LightcurveConfig Dataclass

New dataclass in `core/lightcurve.py`:

```python
@dataclass
class LightcurveConfig:
    enabled: bool = True

    # Data selection
    dataset_type: str = "dia_source_unfiltered"
    min_snr: float = 3.0
    radius: float = 1.0
    band: str | None = None

    # Y-axis
    y_axis: str = "apparent_mag"       # apparent_mag | absolute_mag | flux_nJy | flux_adu
    distance_modulus: float | None = None

    # X-axis
    x_axis: str = "mjd"               # mjd | days_since_explosion
    explosion_mjd: float | None = None

    def validate(self):
        """Raise ValueError if config is inconsistent."""
        ...

    @classmethod
    def from_yaml(cls, yaml_dict: dict, options_dict: dict | None = None):
        """Parse from YAML lightcurve: section, with fallback to options: block."""
        ...
```

`from_yaml` reads from the `lightcurve:` section first, falls back to old `options:` keys for backwards compat, then applies defaults.

## CLI Changes

New flags on `nickel lightcurve`:

```
--y-axis {apparent_mag,absolute_mag,flux_nJy,flux_adu}   (default: apparent_mag)
--x-axis {mjd,days_since_explosion}                       (default: mjd)
--explosion-mjd FLOAT                                     (required with --x-axis days_since_explosion)
--distance-modulus FLOAT                                   (required with --y-axis absolute_mag)
```

These map directly to `LightcurveConfig` fields.

## Changes to extract_lightcurve.py

1. **Accept new CLI arguments** matching the config fields
2. **X-axis:** When `x_axis=days_since_explosion`, compute `days = mjd - explosion_mjd` and add as a column. Plot uses days column instead of mjd.
3. **Y-axis logic:**
   - `apparent_mag`: Current behavior (ADU -> nJy -> AB mag via photoCalib)
   - `absolute_mag`: Same as apparent, then subtract `distance_modulus`
   - `flux_nJy`: Stop at nJy conversion, skip magnitude computation
   - `flux_adu`: Use raw instrumental flux, skip photoCalib entirely
4. **CSV output:** Always includes all columns (mjd, flux, flux_nJy, mag, etc.) regardless of plot mode. The CSV is the full data; plotting config only controls visualization.
5. **Plot:** Adjusts axes labels and orientation based on config.

## Changes to run.py Orchestrator

- Parse new `lightcurve:` section into a `LightcurveConfig` instance
- Fall back to old `options:` keys if `lightcurve:` section absent
- Pass `LightcurveConfig` through to `_run_lightcurve_step()` and into `lightcurve.run()`
- Remove lightcurve-specific fields from `RunConfig` (they move to `LightcurveConfig`)

## Changes to plotting.py

`format_lightcurve_axes()` and `plot_lightcurve_band()` need to handle:

- **Y-axis labels:** "Apparent Magnitude (AB)", "Absolute Magnitude", "Flux (nJy)", "Flux (ADU)"
- **Y-axis inversion:** Only for magnitude modes (brighter = up)
- **X-axis labels:** "MJD", "Days Since Explosion"
- **Negative flux:** For flux modes, show all points. For mag modes, NaN for negative flux (current behavior).

## Files Modified

| File | Change |
|------|--------|
| `core/lightcurve.py` | Add `LightcurveConfig` dataclass, update `run()` signature |
| `core/run.py` | Parse `lightcurve:` section, adapt `RunConfig` |
| `pipeline_tools/extract_lightcurve.py` | New CLI args, y-axis/x-axis logic |
| `cli.py` | New `--y-axis`, `--x-axis`, `--explosion-mjd`, `--distance-modulus` flags |
| `obs_nickel/plotting.py` | Axis formatting for new modes |
| `scripts/config/2023ixf/*.yaml` | Update to use new `lightcurve:` section |

## Non-goals

- No changes to LSST PipelineTasks (they have their own config system)
- No changes to Butler or any running pipeline stages
- No changes to data extraction logic (just how results are displayed)
