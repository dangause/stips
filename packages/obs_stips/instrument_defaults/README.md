# Framework default pipelines & configs (the tiering contract)

This directory ships the **framework-default** pipelines (`pipelines/`) and
config overrides (`configs/`) that every instrument inherits unless it provides
its own copy. Resolution is **instrument-dir-first, else here**
(`Config.resolve_pipeline()` / `resolve_config()` in
`packages/stips/src/stips/core/config.py`): a fork overrides one file by dropping
a same-named file into `instruments/<name>/pipelines/` or
`instruments/<name>/configs/`; everything else falls back to this directory.

## What is tiered where

These defaults are split into two tiers by how instrument-specific they are.

### Neutral (safe to inherit unchanged)

Structural pipeline scaffolding and geometry-agnostic glue:

- `pipelines/*.yaml` — task graphs, connection wiring, subset/step definitions.
  The selection/seeing thresholds in `DRP.yaml`
  (`install_simple_psf.fwhm`, `makeDirectWarp select.*`, `maxPsfFwhm`, `qMax`)
  are a **reference tuning from the Nickel 1-m**. They are structural for
  1m-class work, so they stay in the shared pipeline, but they are honestly
  labeled and a fork should review and override them per-instrument via
  `instruments/<x>/pipelines/` when its optics/cadence differ.
- `configs/makeSkyMap.py` — a rings SkyMap whose **name** bootstrap overrides
  (`-c name=$SKYMAP_NAME`) but whose **geometry** (pixelScale 0.40"/px) is
  inherited silently. A fork with a materially different plate scale should ship
  its own (see `instruments/ctio1m/configs/makeSkyMap.py`, 0.289"/px).
- `configs/dia/*.py`, `configs/coadds/makeDirectWarp_relaxed.py` — DIA/coadd
  kernel and warp-selection tunings. Reference tunings from the Nickel 1-m,
  resolved instrument-dir-first.
- `configs/filter_map.py` — reference band → refcat-column map covering the
  Nickel and CTIO filter inventories. A fork with a different filter set or
  refcat should override it.
- `configs/apply_colorterms.py`,
  `configs/analysisToolsPhotometricCatalogMatchVisit.py`,
  `configs/refcats_gaia_ps1.py` — **instrument-aware** glue: they load the active
  instrument's `configs/colorterms.py` (via `$INSTRUMENT_DIR`) when present and
  fall back to a neutral, no-op default otherwise (see below).

### Instrument-fitted (MUST be reviewed by a fork — do NOT inherit blindly)

Photometric calibration is empirically fit per telescope and **must not** be
inherited from another instrument. These now live under
`instruments/nickel/configs/` (the reference profile) and are **absent** from
this neutral tier:

- `colorterms.py` — PS1/Gaia/MONSTER → instrument-band color terms, fit against
  Landolt standards. The neutral default here is an **empty** library.
- `calibrateImage/tuned_configs/*.py` — per-field/per-campaign `calibrateImage`
  tunings (`dense_strict`, `2023ixf_*`, `2020wnt_*`, `best_calib_t071`, ...).
- `refcats_gaia_ps1.py` — the full Nickel band → PS1 column overlay. The neutral
  default here **derives** the PS1 filterMap from the active profile's
  `ps1_band_map` instead.

## The empty-colorterms contract

`applyColorTerms=True` with an empty color-term library raises a
`FieldValidationError` in the stack at graph-build time. So the neutral glue
files enable color terms **only when the resolved library is non-empty**:

- A fork that ships `instruments/<name>/configs/colorterms.py` gets color terms
  ON, loaded from its own file.
- A fork that ships none inherits the empty neutral `colorterms.py`, and color
  terms stay OFF — calibration falls back to a plain per-visit zeropoint (no
  color correction) rather than crashing.

**A new fork's #1 review item is photometric calibration.** Fit your own color
terms and drop `colorterms.py` (and, if you use the Gaia+PS1 refcat path, a
`refcats_gaia_ps1.py`) into `instruments/<name>/configs/`. Until you do, your
photometry has no color correction.

## How overrides resolve (quick reference)

| File | Neutral default (here) | Nickel (reference) |
|------|------------------------|--------------------|
| `colorterms.py` | empty library | `instruments/nickel/configs/colorterms.py` |
| `calibrateImage/tuned_configs/*` | absent | `instruments/nickel/configs/calibrateImage/tuned_configs/*` |
| `refcats_gaia_ps1.py` | derives PS1 map from profile | `instruments/nickel/configs/refcats_gaia_ps1.py` |
| `filter_map.py` | reference map (+U for CTIO) | inherits neutral |
| `apply_colorterms.py` | instrument-aware, off if empty | inherits neutral |
| `makeSkyMap.py` | reference geometry (0.40"/px) | inherits neutral |
| `DRP.yaml` thresholds | reference (Nickel-derived) | inherits neutral |
