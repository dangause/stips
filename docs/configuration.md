# Configuration

STIPS has **one** config source: the YAML file you pass with the group-level
`-c/--config` flag. Its `env:` block supplies paths, and the rest of the file
drives `stips run`. There are no `.env` files, no `-p/--profile` flag, and no
`os.environ` fallback for config values.

```bash
# Show and validate the configuration, then run a step with it
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml env
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml calibs 20230519
```

Per-target configs live in `scripts/config/<target>/`. Each one is
self-contained, so switching targets means passing a different file.

## The `env:` block

```yaml
env:
  REPO: /path/to/butler/repo
  STACK_DIR: /path/to/lsst_stack
  INSTRUMENT_DIR: /path/to/stips/instruments/nickel
  RAW_PARENT_DIR: /path/to/raw/data        # contains YYYYMMDD/raw/
  REFCAT_REPO: /path/to/refcats            # optional
  CP_PIPE_DIR: "${STACK_DIR}/cp_pipe"      # optional
  # CCD_BINNING: 2                         # optional; for 2x2-binned raws
```

`${VAR}` references expand against other keys in the same block.

### Required keys

| Key | Description |
|---|---|
| `REPO` | Path to the Butler repository |
| `STACK_DIR` | Path to the LSST stack installation |
| `INSTRUMENT_DIR` | Path to the active instrument profile directory (e.g. `instruments/nickel`, `instruments/ctio1m`); must contain `profile.py` |
| `RAW_PARENT_DIR` | Parent directory for raw data (contains `YYYYMMDD/raw/`) |

### Optional keys

| Key | Description |
|---|---|
| `REFCAT_REPO` | Path to a reference catalog repository |
| `CP_PIPE_DIR` | Path to `cp_pipe`; auto-discovered from the stack if unset |
| `CCD_BINNING` | On-chip binning factor; scales the camera geometry (default `1`) |
| `LICK_ARCHIVE_DIR` | Path to the Lick archive client (Nickel `download`) |
| `NOIRLAB_PROPOSAL` | Proposal-id filter for the CTIO NOIRLab `download` |

:::{admonition} Removed keys
:class: warning
`INSTRUMENT_PACKAGE` and `OBS_NICKEL` are gone. A lingering
`INSTRUMENT_PACKAGE` raises an error telling you to set `INSTRUMENT_DIR`
to the directory containing your instrument's `profile.py`.
:::

## The pipeline sections

`stips run` reads the rest of the file to orchestrate a whole campaign.

```yaml
object: "2023ixf"       # partial, case-insensitive match on FITS OBJECT
ra: 210.910750          # full TNS precision — see below
dec: 54.311694
bands: ["r", "i"]

template:
  type: ps1             # ps1 | coadd | skymapper | auto | none
  size: 0.4             # PS1 cutout size in degrees
  degrade_seeing: 2.0   # optional: convolve PS1 to match the science seeing
  nights: [...]         # coadd type only: SN-free template nights

science:
  nights: [20230519, 20230521, 20230523]

configs:                # optional; resolved instrument-dir-first
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/dense_relaxed.py
      - calibrateImage/tuned_configs/sparse_relaxed.py
    colorterms: apply_colorterms.py
  dia:
    subtract_images: dia/subtractImages_ps1.py
    detect_and_measure: dia/detectAndMeasure.py

options:
  jobs: 6
  concurrent_nights: 3
  forced_phot: true
  forced_phot_image_type: diffim   # visit | diffim | both
  continue_on_error: true
  use_fallbacks: true              # retry with fallback configs

lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec
  min_snr: 2
  max_mag_err: 1.0
  y_axis: apparent_mag             # or absolute_mag, flux_nJy, flux_adu
  x_axis: days_since_explosion     # or mjd
  explosion_mjd: 60082.75          # needed for days_since_explosion
  # distance_modulus: 29.05        # needed for absolute_mag
```

:::{admonition} Use full-precision coordinates
:class: tip
Convert the target's TNS sexagesimal position to decimal degrees with 6+
decimal places (e.g. `14:03:38.580, +54:18:42.10` →
`210.910750, 54.311694`). Rounding to 2 decimals is a 5–17″ offset —
enough to miss a point source on Nickel's 0.37″/pixel scale. The symptom
is uniformly negative forced-photometry flux.
:::

### Template types

| `template.type` | Bands | When to use |
|---|---|---|
| `ps1` | r, i | Northern fields (Dec ≳ −30°). The default for most campaigns. |
| `coadd` | all | A same-instrument coadd from SN-free nights. Preferred for southern fields. |
| `skymapper` | r, i | Southern fields with no SN-free epochs. Explicit only — see [SkyMapper templates](skymapper-template-validation.md). |
| `auto` | all | PS1 for the PS1-eligible bands, a coadd from `template.nights` for the rest. Never selects SkyMapper. |
| `none` | — | Skip templates entirely (calibs + science only, no DIA). |

## Pipeline and config resolution

Pipelines and config overrides resolve **instrument directory first, then the
framework default**. A fork overrides one file by dropping a same-named file
into its own `instruments/<name>/pipelines/` or `configs/`; everything else
inherits the defaults in `packages/obs_stips/instrument_defaults/`. The
[science configs page](science-configs.md) covers the `calibrateImage` tuning
files, and [Adding a telescope](forking-stips.md) covers what a fork must
review.

## Butler collections

Collection names come from the profile's `collection_prefix` (`Nickel` for the
reference profile). Downstream steps should read the **CHAINED parent**
`processCcd/{ts}`, which includes the primary config and any fallback runs.

| Collection | Type | Contents |
|---|---|---|
| `Nickel/raw/{night}/{ts}` | RUN | Ingested raws |
| `Nickel/cp/{night}/{bias,flat}/{ts}/run` | RUN | Constructed calibs |
| `Nickel/calib/{night}` | CALIBRATION | Certified calibrations |
| `Nickel/calib/current` | CHAINED | Unified calibration chain |
| `Nickel/calib/curated` | CHAINED | Camera geometry and defects |
| `Nickel/runs/{night}/processCcd/{ts}` | CHAINED | Science outputs — **use this** |
| `Nickel/runs/{night}/processCcd/{ts}/run` | RUN | Primary `calibrateImage` config |
| `Nickel/runs/{night}/processCcd/{ts}/run_fb1` | RUN | Fallback 1, if used |
| `Nickel/runs/{night}/diff/{ts}/run` | RUN | Difference imaging |
| `Nickel/runs/{night}/forcedPhotRaDec/{ts}/diffim_{band}` | RUN | Forced photometry on difference images |
| `templates/ps1/{band}` | RUN | PS1 templates |
| `templates/deep/tract{N}/{band}` | RUN | Coadd templates |

## Observing night vs. UT day

Collections use the **local observing night** for readability; Butler queries
use the UT `day_obs`. The profile's `night_to_dayobs_offset_days` maps one to
the other (`1` for both Nickel and CTIO: night `20230519` → `day_obs`
`20230520`).
