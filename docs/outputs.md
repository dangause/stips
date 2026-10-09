# Outputs

A run writes to three places:

| Where | What |
|---|---|
| The Butler repository, `REPO` | Raw frames, calibrations, processed images and catalogs, templates, difference images, forced photometry |
| `REPO/lightcurves/` | Lightcurve tables and plots, period and transit results |
| `logs/<run id>/`, beside your `instruments/` directory | A log for every step; see {doc}`logging` |

## Lightcurves

`stips run` writes `lightcurve_<object>.csv` and a matching `.png` plot to
`REPO/lightcurves/`. Each row is one measurement:

| Column | Meaning |
|---|---|
| `mjd`, `band`, `visit` | When, in which band, and which exposure |
| `flux_nJy`, `flux_nJy_err` | Calibrated flux and its error, in nanojanskys |
| `mag`, `mag_err` | Magnitude and its error |
| `flux`, `flux_err` | Instrumental flux, in ADU |
| `snr` | Signal-to-noise ratio |
| `ra`, `dec`, `separation_arcsec` | Where the measurement was made, and its distance from the target |

Magnitudes are AB, except that the Nickel profile puts B, V, R, and I on the
Vega system when calibrating with `gaia_ps1`; the plot labels the system.
`lightcurve.max_mag_err` removes noisy points from the plot only, and the CSV
keeps every measurement. Variable-star and transit runs add the files
described in {doc}`time-series`.

## The Butler repository

Everything else lives in the repository as Butler datasets, grouped into
collections. Names start with the profile's `collection_prefix`, `Nickel`
for the reference profile.

| Collection | Contents |
|---|---|
| `Nickel/raw/<night>/<ts>` | Ingested raw frames |
| `Nickel/calib/current` | All certified calibrations (chained) |
| `Nickel/runs/<night>/processCcd/<ts>` | Calibrated exposures and source catalogs (chained; read this one) |
| `Nickel/runs/<night>/processCcd/<ts>/run_fb1` | Exposures that needed the first fallback config |
| `Nickel/runs/<night>/diff/<ts>/run` | Difference images and difference-image sources |
| `Nickel/runs/<night>/forcedPhotRaDec/<ts>/diffim_<band>` | Forced photometry on difference images |
| `Nickel/runs/<night>/forcedPhotRaDec/<ts>/visit_<band>` | Forced photometry on direct images |
| `templates/ps1/<band>`, `templates/deep/tract<N>/<band>` | PS1 and coadd templates |

`<ts>` is the timestamp of the run that wrote the collection, so rerunning a
night adds new collections beside the old ones. Science outputs use a
*chained* collection that combines the primary `run` with any fallback runs;
always read the chained parent.

To look inside, activate the stack and use the [`butler`
command](https://pipelines.lsst.io/modules/lsst.daf.butler/scripts/butler.html):

```bash
source $STACK_DIR/loadLSST.sh && setup lsst_distrib
butler query-collections $REPO "Nickel/runs/20230519/*"
butler query-datasets $REPO difference_image --collections "Nickel/runs/20230519/diff/*"
butler retrieve-artifacts $REPO ./diffims -d difference_image --collections "Nickel/runs/20230519/diff/*"
```

The last command copies the FITS files out for viewing in DS9 or similar.

## Processing logs

`REPO/processing_log/<night>_<step>.json` records, for each night and step,
which `calibrateImage` configs were tried, how many exposures each processed,
and which failed. It is the quickest way to see which nights needed a
fallback.

## Cleaning up

`stips clean` removes processing runs so you can rerun steps. It keeps raw
frames, calibrations, reference catalogs, and sky maps unless told otherwise:

```bash
stips -c target.yaml clean --dry-run                      # list what would go
stips -c target.yaml clean --step dia --step fphot -y     # only DIA and photometry
stips -c target.yaml clean --night 20230519 -y            # one night
```
