# Variable stars and transits

STIPS was built for supernovae, but the same reduction measures any source at
fixed coordinates. `options.pipeline_type` adapts the run to the target:

| | `supernova` (default) | `variable` | `transit` |
|---|---|---|---|
| Forced photometry on | Difference images | Difference and direct images | Direct images |
| Extra photometry | | | Differential aperture photometry against comparison stars |
| Search | | Lomb–Scargle period search, if `period_search: true` | Box least-squares (BLS) transit search |

`forced_phot_image_type` overrides the first row.

## Variable stars

```yaml
template:
  type: coadd
  nights: [...]          # spanning several cycles: the coadd approximates the mean
options:
  pipeline_type: variable
  period_search: true
  period_min: 0.1        # days
  period_max: 100.0      # days
  period_samples: 10000  # frequency grid size
```

The period search runs on the extracted lightcurve, normalizing each band
before combining them, and writes to `lightcurves/period_analysis/` in the
repository: `period_results.json` (best period, power, false-alarm
probability), `periodogram.png`, `lightcurve.png`, and `phase_folded.png`.

## Exoplanet transits

```yaml
template:
  type: none                  # no subtraction: transits are measured on direct images
options:
  pipeline_type: transit
  skip_dia: true              # required with type: none; see Templates
  period_min: 0.5             # days
  period_max: 10.0
  transit_duration_min: 0.5   # hours
  transit_duration_max: 6.0   # hours
```

A transit is a fractional drop in the host star's total flux, so transit mode
measures the star on the direct images rather than on difference images. It
also runs differential aperture photometry, dividing the target's
flux by that of comparison stars in the same frame to cancel transparency
changes, and writes `lightcurves/differential_<object>.csv`. The BLS search
runs on that lightcurve and writes to `lightcurves/transit_analysis/`:
`transit_results.json` (period, depth, duration, signal-to-noise),
`bls_periodogram.png`, `lightcurve.png`, and `phase_folded_transit.png`.

Give the host star's position at the epoch of observation. Nearby stars can
have large proper motions (HD 189733 moves about 0.25″ per year), and a stale
position can miss the target in the differential step.

## Examples

Annotated templates and real campaigns in
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config):

- `example_variable_star/`, `cy_aqr/`, `dy_peg/`, `ac_and/`: variable stars.
- `example_exoplanet/`, `hd189733/`: transits.
