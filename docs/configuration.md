# Configuration

Each target has one YAML file, passed to every command with `-c`. The `env:`
block says where things are; the other sections say what to process. There
is no other configuration source: no `.env` files and no environment
variables.

```bash
stips -c target.yaml env            # show the resolved paths and any problems
stips -c target.yaml run            # process the whole campaign
```

The {doc}`quickstart` has a complete example, and
[`scripts/config/`](https://github.com/dangause/stips/tree/main/scripts/config)
has many more.

## `env`

| Key | Required | Meaning |
|---|---|---|
| `REPO` | yes | Butler repository; created by the first run |
| `STACK_DIR` | yes | Rubin stack installation: the directory containing `loadLSST.sh` |
| `INSTRUMENT_DIR` | yes | Instrument profile directory, containing `profile.py` |
| `RAW_PARENT_DIR` | yes | Raw data, as `<night>/raw/*.fits` |
| `REFCAT_REPO` | for bootstrap | MONSTER shard directory; see {doc}`reference-catalogs` |
| `CP_PIPE_DIR` | no | `cp_pipe` location; found from the stack if unset |
| `CCD_BINNING` | no | On-chip binning factor of the raws, such as `2`; default `1` |
| `LICK_ARCHIVE_DIR` | Nickel `download` | The Lick archive client, normally `instruments/nickel/vendor/lick_searchable_archive` |
| `NOIRLAB_PROPOSAL` | no | Restrict CTIO `download` to one proposal ID |

Values can refer to other keys in the block, as in
`CP_PIPE_DIR: "${STACK_DIR}/cp_pipe"`. The old `INSTRUMENT_PACKAGE` key is
rejected with a message to use `INSTRUMENT_DIR`.

## Target

| Key | Meaning |
|---|---|
| `object` | Selects frames by `OBJECT` header: per night, the one value containing it, or the exact match if several do |
| `ra`, `dec` | Target position in decimal degrees, at full precision (six or more decimals) |
| `bands` | Bands to process, using the profile's names (Nickel: `b`, `v`, `r`, `i`, …) |

## `science`

| Key | Meaning |
|---|---|
| `nights` | Observing nights to process, as `YYYYMMDD` local dates |

## `template`

| Key | Default | Meaning |
|---|---|---|
| `type` | `ps1` | `ps1`, `coadd`, `auto`, `skymapper`, or `none`; see {doc}`templates` |
| `size` | `0.3` | Survey cutout side, in degrees |
| `degrade_seeing` | | Blur a survey template to this FWHM, in arcsec |
| `nights` | | Template nights, for `coadd` and `auto` |
| `mjd_start`, `mjd_end` | | Restrict survey frames to an MJD range |
| `unity_photocalib` | `false` | Force the PS1 template's photometric calibration to 1 |

## `refcat`

| Key | Default | Meaning |
|---|---|---|
| `mode` | `monster` | `monster`, `gaia_ps1`, or `gaia`; see {doc}`reference-catalogs` |
| `radius_deg` | `0.3` | Radius of the cone fetched around `ra`/`dec` |
| `gaia_quality` | | Gaia cuts, such as `{ruwe_max: 1.4, require_5param: true}` |

## `configs`

Override the configuration of individual pipeline tasks. Each path is looked
up in the instrument's `configs/` directory first, then in the framework
defaults (`packages/obs_stips/instrument_defaults/configs/`).

| Key | Task |
|---|---|
| `science.calibrate_image` | `calibrateImage`; see {doc}`science-configs` |
| `science.calibrate_image_fallbacks` | Configs to retry failed exposures with, in order |
| `science.colorterms` | Colour terms for photometric calibration |
| `dia.subtract_images` | Image subtraction |
| `dia.detect_and_measure` | Detection and measurement on difference images |
| `coadd.make_direct_warp`, `coadd.select_template_coadd_visits`, `coadd.select_deep_coadd_visits` | Coadd templates |

## `options`

| Key | Default | Meaning |
|---|---|---|
| `jobs` | `8` | Parallel processes per step |
| `concurrent_nights` | `0` | Nights processed at once; `0` processes them one after another |
| `continue_on_error` | `true` | Keep going when a night or band fails |
| `use_fallbacks` | `true` | Retry failed exposures with `calibrate_image_fallbacks` |
| `skip_calibs`, `skip_science`, `skip_dia` | `false` | Skip a stage for every night |
| `rebuild_templates` | `false` | Re-fetch survey templates that already exist; coadd templates are rebuilt every run |
| `forced_phot` | `true` | Run forced photometry |
| `forced_phot_image_type` | depends on `pipeline_type` | `diffim`, `visit`, or `both` |
| `pipeline_type` | `supernova` | `supernova`, `variable`, or `transit`; see {doc}`time-series` |
| `period_search`, `period_min`, `period_max`, `period_samples` | `false`, `0.1`, `100`, `10000` | Lomb–Scargle period search; periods in days |
| `transit_search`, `transit_duration_min`, `transit_duration_max` | on for `transit`, `0.5`, `6` | BLS transit search; durations in hours |
| `execution`, `site` | `local`, `local` | Run on a cluster; see {doc}`hpc` |
| `container_image` | | Apptainer image, for the `singularity-slurm` site |
| `bps_poll_interval`, `bps_timeout` | `5`, `7200` | Cluster status polling and per-stage timeout, in seconds |

## `lightcurve`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Extract a lightcurve at the end of the run |
| `dataset_type` | `dia_source_unfiltered` | `forced_phot_diffim_radec` (forced photometry, recommended) or `dia_source_unfiltered` (DIA detections) |
| `min_snr` | `3` | Drop measurements below this signal-to-noise ratio |
| `max_mag_err` | | Hide points with larger errors from the plot; the CSV keeps them |
| `radius` | `1.0` | Match radius around the target, in arcsec |
| `band` | all | Only this band |
| `y_axis` | `apparent_mag` | `apparent_mag`, `absolute_mag`, `flux_nJy`, or `flux_adu` |
| `distance_modulus` | | Needed for `absolute_mag` |
| `x_axis` | `mjd` | `mjd` or `days_since_explosion` |
| `explosion_mjd` | | Needed for `days_since_explosion` |
