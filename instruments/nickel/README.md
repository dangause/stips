# Nickel — reference instrument definition

This is the **declarative definition** of the Nickel 1-meter telescope (Lick
Observatory) — the STIPS reference instrument. There is **no** `lsst.obs.nickel`
Python package: the generic `obs_stips` package synthesizes the LSST instrument
machinery (instrument / translator / raw formatter) from the profile below,
late-bound at runtime from `INSTRUMENT_DIR`.

A telescope is defined entirely by the files in this directory:

| File / dir        | Purpose                                                        |
|-------------------|---------------------------------------------------------------|
| `profile.py`      | `InstrumentProfile` (name, site, filters, header translation hooks, `instrument_class`, `obs_data_package`) — loaded **by path** |
| `camera/`         | Camera geometry yaml (loaded from `INSTRUMENT_DIR`)            |
| `fetch.py`        | Optional Lick-archive data-fetch hook (referenced by the profile) |
| `template_metadata.json` | PS1 template metadata for this instrument              |
| `tests/`          | Reference-instrument tests, run against the generic machinery |
| `configs/`        | Nickel's **instrument-fitted** science calibration — Landolt-fit `colorterms.py`, `calibrateImage/tuned_configs/*`, and the Nickel-band `refcats_gaia_ps1.py` (resolved instrument-dir-first). These are per-telescope and are deliberately **not** in the framework's neutral tier; a fork must fit and drop in its own — see `packages/obs_stips/instrument_defaults/README.md` |
| `pipelines/`      | *Optional, absent here.* Nickel inherits all framework-default pipelines from `obs_stips/instrument_defaults/pipelines/`; a fork drops a same-named file to override one |
| `colorterms/`, `tuning/`, `defects/` | Recipes/utilities that regenerate the fitted `configs/` assets (`stips-colorterms-fit`, `stips-tune-calibrate-image`, `stips-defects-build`) |

## Using it

Point `INSTRUMENT_DIR` at this directory (typically via the `env:` block of a
`stips -c <config.yaml>`); the framework loads `profile.py` by path and Butler
registers `lsst.obs.stips.active.Instrument` (which resolves to "Nickel"):

```bash
export INSTRUMENT_DIR=/path/to/stips/instruments/nickel
butler register-instrument <repo> lsst.obs.stips.active.Instrument
```

Curated calibrations (defects/crosstalk) come from the co-located
`obs_nickel_data` EUPS data package (`instruments/nickel/obs_nickel_data`),
named by `profile.obs_data_package`.

To define a new telescope, copy this directory and edit `profile.py` +
`camera/`. See `docs/forking-stips.md`.
