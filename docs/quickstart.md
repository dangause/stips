# Quickstart

This walks through a first reduction: three nights of SN 2023ixf, a Type II
supernova in M101, taken with the Nickel 1-m in May 2023 and public in the
Lick archive. It ends with a lightcurve in Nickel's Sloan-like r′ and i′
filters, which the Nickel profile calls `rp` and `ip`.

You need a {doc}`native install <installation>` of STIPS and MONSTER
reference-catalog shards covering M101 (see {doc}`reference-catalogs`).

## 1. Write the config

Save this as `sn2023ixf.yaml` and replace the `/home/you` and `/data` paths
with yours:

```yaml
env:
  REPO: /data/stips/sn2023ixf_repo              # created by the first run
  STACK_DIR: /home/you/lsst_stack
  INSTRUMENT_DIR: /home/you/stips/instruments/nickel
  RAW_PARENT_DIR: /data/raw
  REFCAT_REPO: /data/refcats
  LICK_ARCHIVE_DIR: /home/you/stips/instruments/nickel/vendor/lick_searchable_archive

object: "2023ixf"           # matched against the FITS OBJECT header
ra: 210.910750              # full precision, from TNS
dec: 54.311694
bands: ["rp", "ip"]         # Nickel's r′ and i′ filters

refcat:
  mode: gaia_ps1            # fetch Gaia and Pan-STARRS for this field

template:
  type: ps1                 # Pan-STARRS1 template images
  size: 0.4                 # degrees; covers the field and its dithers

science:
  nights: [20230519, 20230527, 20230531]

configs:                    # Nickel's tuned calibration and subtraction configs
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/dense_relaxed.py
      - calibrateImage/tuned_configs/sparse_relaxed.py
    colorterms: apply_colorterms.py
  dia:
    subtract_images: dia/subtractImages_ps1.py

lightcurve:
  dataset_type: forced_phot_diffim_radec
  min_snr: 1
  x_axis: days_since_explosion
  explosion_mjd: 60082.75
```

Check it with `stips -c sn2023ixf.yaml env`. It lists paths that do not
exist yet: `REPO`, which the first run creates, and `RAW_PARENT_DIR` until the
download in the next step. It checks the stack only once every path
exists.

## 2. Download the raw frames

```bash
stips -c sn2023ixf.yaml download
```

This fetches every night listed in the config into
`RAW_PARENT_DIR/<night>/raw/`: biases, flats, and science frames.

## 3. Run

Preview the plan, then run it:

```bash
stips -c sn2023ixf.yaml run --dry-run
stips -c sn2023ixf.yaml run
```

The run creates the repository and fetches reference stars and PS1
templates. Then, for every night, it builds calibrations, processes the
science frames, subtracts the templates, and measures the supernova. It
prints where its logs are, `logs/<run id>/`, and ends with a summary of what
succeeded.

## 4. Look at the results

```text
/data/stips/sn2023ixf_repo/lightcurves/
├── lightcurve_2023ixf.csv     # one row per measurement
└── lightcurve_2023ixf.png     # magnitude against days since explosion
```

The difference images, catalogs, and calibrations stay in the Butler
repository. {doc}`outputs` explains where everything is and how to query it.

## Running steps one at a time

`run` chains the individual commands (`bootstrap`, `calibs`, `science`,
`dia`, `fphot`, and `lightcurve`), which are useful for redoing one night or
band. They take most settings from their own flags rather than from the
config's sections; see {doc}`reference/cli`.

## Next steps

- {doc}`new-campaign`: set up your own target.
- {doc}`templates`: choose a template for a field without Pan-STARRS coverage
  or for bands Pan-STARRS does not have.
- {doc}`configuration`: every option in the config file.
