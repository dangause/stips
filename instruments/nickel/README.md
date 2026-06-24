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
| `configs/`, `pipelines/` | *Optional.* Tuned config / pipeline overrides. Absent here — Nickel inherits the framework defaults from `obs_stips/instrument_defaults/`; a fork drops a same-named file to override one |

## Using it

Point `INSTRUMENT_DIR` at this directory (typically via the `env:` block of a
`stips -c <config.yaml>`); the framework loads `profile.py` by path and Butler
registers `lsst.obs.stips.active.Instrument` (which resolves to "Nickel"):

```bash
export INSTRUMENT_DIR=/path/to/stips/instruments/nickel
butler register-instrument <repo> lsst.obs.stips.active.Instrument
```

Curated calibrations (defects/crosstalk) still come from the separate
`obs_nickel_data` EUPS data package, named by `profile.obs_data_package`.

To define a new telescope, copy this directory and edit `profile.py` +
`camera/`. See `docs/forking-stips.md`.
