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

### Trimming the science step to what the lightcurve path needs

Transit and variable-star campaigns don't read most of what the science
step's full `stage1-single-visit` subset produces: the lightcurve path only
needs `calibrateImage`'s per-detector outputs (`preliminary_visit_image`,
`single_visit_star_unstandardized`) and `consolidateVisitSummary`'s
`preliminary_visit_summary`. The rest of the subset is analysis_tools plots
and metrics for per-visit, per-tract and survey-wide QA that forced
photometry, differential photometry and `stips calib-metrics` never consume.
On a measured Y4KCam night, `isr` took 37 s and `calibrateImage` 115 s per
frame, but the whole science step cost about 470 core-seconds per frame --
the difference is those analysis_tools tasks. Set

```yaml
configs:
  science:
    pipeline_labels: "step1a-single-visit-detectors,consolidateVisitSummary"
```

to run only that minimal set (`stips.core.science.TRANSIT_SCIENCE_LABELS`).
This is an explicit opt-in -- existing campaigns that rely on the full QA
subset are unaffected until they set it.

### Comparison star normalisation

Each selected comparison star has its own reference flux (the median of its
aperture flux over the visits where it is detected, ignoring any NaN, None
or non-positive measurement). The per-visit comparison signal combines the
comparisons actually present in that visit as a *flux-weighted ratio of
sums*: `comp_signal = Σ c_i / Σ ref_i`, summed over the present comparison
stars only. This matters because the comparison ensemble is not always
complete: when one of the selected comparison stars drops below the
per-frame detection threshold (poor seeing, clouds), summing only the raw
fluxes of whichever stars remain shrinks the denominator and inflates the
target's differential flux by roughly `n_selected / n_present` on that
frame — the bug found while validating the Y4KCam WASP-19 transit of
2011-12-24 against Cortés-Zuleta et al. (2020), where 63 of 379 frames had
3–9 of 10 comparisons present and showed exactly this `10 / n_comps`
inflation. Dividing by `Σ ref_i` over the same present stars removes that
inflation: a missing comparison drops both its flux and its reference flux
from the ratio, changing the signal's noise, not its level. Whenever every
comparison star is present, `Σ ref_i` is the same constant on every visit,
so `comp_signal` reduces to `Σ c_i` rescaled by that constant — a factor the
light curve's median normalisation removes, reproducing the pre-fix
behaviour exactly in that case. The `comp_sum` output column keeps its name
but now holds this flux-weighted ratio (`Σ c_i / Σ ref_i`, ≈1.0 for a
complete, stable ensemble), not a flux sum or a mean of relative fluxes.
One config field controls this: `minComparisonFraction` (default 0.7, a
`RangeField` in [0.0, 1.0]) drops a visit outright when fewer than that
fraction of the *usable* selected comparison stars (those with a valid
reference flux) are detected in it, rather than normalising against a
degraded ensemble. A peak-count cut on comparison candidates (`maxComparisonPeak`) is not implemented (see the TODO at
the candidate-selection site in `differentialPhot.py`) because the star
catalogs available to this task carry no raw peak-pixel or non-linearity
column to check against.

The ensemble *selection* itself (which comparison stars are "usable" in
the first place) ranks candidates by the RMS of their per-visit aperture
flux and keeps the most stable ones. That ranking is computed over the
same finite, positive subset used for the reference flux above: a single
NaN, None or non-positive measurement in an otherwise-stable candidate
does not corrupt its RMS (and does not produce a NaN sort key, which is
otherwise undefined and can silently rank the best candidate, and
anything sorted after it, out of the ensemble). A candidate with no valid
measurement in any visit can't be ranked at all and is excluded with a
warning naming it.

### Re-running the differential photometry

To re-run only the differential-photometry step on an existing repository
(no new calibration, image processing, or forced photometry), run the
pipeline directly against the existing `calibrateImage`/science collections
for the night:

```sh
pipetask run \
  -b <REPO> \
  -p <stack>/obs_stips/instrument_defaults/pipelines/DifferentialPhot.yaml \
  -i <prefix>/runs/<night>/processCcd/<chain>,<prefix>/calib/current,refcats,<skymap_collection> \
  -o <prefix>/runs/<night>/differentialPhot \
  -c differentialPhot:targetRa=<RA_DEG> \
  -c differentialPhot:targetDec=<DEC_DEG> \
  -c differentialPhot:targetName=<OBJECT> \
  -c differentialPhot:bandFilter=<BAND> \
  -c differentialPhot:minComparisonFraction=0.7 \
  --register-dataset-types \
  --clobber-outputs
```

`-o` is the same chained-collection name every time (`CollectionNames.differential_phot`
has no run timestamp), so repeated runs are non-destructive: `pipetask`
writes each run into a new timestamped `RUN` collection and chains it in
front, it does not overwrite prior output. Omit `-c differentialPhot:bandFilter=...`
when processing more than one band. **Prefer this `pipetask run` form for a
pure re-run** of the differential-photometry step alone.

The `stips -c <config.yaml> run` CLI route is *not* equivalent to the
command above: it is a full pipeline run that happens to include the
differential-photometry step, not a way to re-run that step in isolation.
Concretely, with

```yaml
template:
  type: none            # skip the template-building step entirely
options:
  pipeline_type: transit
  skip_calibs: true     # skip calibration
  skip_science: true    # skip calibrateImage/processCcd
  skip_dia: true         # required with template.type: none; see Templates
  forced_phot: false     # skip forced photometry
```

`stips -c <config.yaml> run` is a full pipeline run that happens to include
the differential-photometry step; it still runs these steps even with
every `skip_*` option above set: (1) the bootstrap check, which initializes
the Butler repository (and runs a MONSTER refcat ingest) if it is not
already set up; (2) resolving or fetching the reference catalog (the
refcat step is not gated by any of the `skip_*` options above); (3) if
`template.type` is anything other than `none`, the template step, which
only *builds the templates that are missing* -- it does not overwrite
existing ones unless `rebuild_templates: true` is set; (4) `_run_lightcurve_step`,
which extracts a light curve from forced photometry or DIA sources (this
is a separate step/output from the differential-photometry lightcurve,
and runs regardless of `pipeline_type`); (5) `_run_differential_phot_step`,
which resolves the same input collections from the existing repository and
runs a `pipetask run` command equivalent to the one above (including
`-c differentialPhot:minComparisonFraction=<options.min_comparison_fraction>`,
default 0.7), then exports `lightcurves/differential_<object>.csv`; and
(6) the transit (BLS) search over the resulting light curve. There is no
dedicated `stips` CLI subcommand for the differential-photometry step
alone today.

## Examples

Annotated templates and real campaigns in
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config):

- `example_variable_star/`, `cy_aqr/`, `dy_peg/`, `ac_and/`: variable stars.
- `example_exoplanet/`, `hd189733/`: transits.
