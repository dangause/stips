# Changelog

All notable changes to STIPS (the Small Telescope Image Processing Suite) are documented here.

## [Unreleased]

### Defaults tiering: Nickel-fitted science calibration moved out of the framework tier (F-012)
- **Moved to `instruments/nickel/configs/`** (behavior for Nickel unchanged —
  instrument-dir-first resolution finds them there): the Landolt-fit
  `colorterms.py`, all `calibrateImage/tuned_configs/*.py`, and the Nickel-band
  `refcats_gaia_ps1.py`.
- **Neutral framework defaults** in `obs_stips/instrument_defaults/configs/`:
  `colorterms.py` is now an **empty** library; `apply_colorterms.py`,
  `analysisToolsPhotometricCatalogMatchVisit.py`, and `refcats_gaia_ps1.py` are
  instrument-aware — they load the active instrument's `configs/colorterms.py`
  / `configs/filter_map.py` via `$INSTRUMENT_DIR` when present and enable color
  terms **only when the resolved library is non-empty** (an empty library with
  `applyColorTerms=True` fails LSST config validation). The neutral
  `refcats_gaia_ps1.py` derives its PS1 filterMap from the profile's
  `ps1_band_map`.
- `filter_map.py` now covers CTIO 1.0m's uppercase `U` physical filter
  (previously a live KeyError for analysis tasks on U-band data).
- DRP.yaml/dia/coadd/skymap threshold comments relabeled honestly as
  "reference tuning from the Nickel 1-m"; new
  `packages/obs_stips/instrument_defaults/README.md` documents the tiering
  contract (what a fork inherits vs MUST review — photometric calibration!).

### QA task-label rename: `...Nickel` → `...Visit` (F-013)
- Renamed 5 analysis/QA task labels in DRP.yaml /
  analysis-visit-single-visit.yaml / visit-quality-detector.yaml
  (`analyzeCalibrateImageMetadataNickel` → `...MetadataVisit`,
  `*SingleVisitStar{Astrometric,Photometric}RefMatchNickel` → `...RefMatchVisit`).
  Task labels become dataset-type names in every fork's Butler repo.
- **Migration:** no data loss; reruns write under the new label-derived dataset
  names; dashboards/queries referencing the old `..Nickel_metadata/_log/_config`
  names must update. See `docs/migrations.md`.

### Crosstalk for multi-amplifier instruments
- **Declarative crosstalk**: instrument profiles can carry a `CrosstalkSpec`
  (N×N coefficient matrix + units). STIPS builds a `CrosstalkCalib`, certifies it
  into `{prefix}/calib/crosstalk` (chained into the curated calib chain), and
  auto-enables ISR `doCrosstalk` — no forked pipelines.
- **Measurement** (`stips measure-crosstalk <nights…>`): derives coefficients from
  exposures via cp_pipe's `cpCrosstalk` pipeline (reusing the profile's
  `isr_overrides` on the measurement ISR), certifies the result, and exports the
  matrix (ECSV) for inspection. Run once when no coefficients are known.
- **CTIO1m / Y4KCam** ships a **measured** 4×4 matrix (derived with
  `measure-crosstalk` on the E2 standard field, night 20111113; ~0.1–0.4%,
  largest between adjacent quadrants). Re-measure on a denser field to tighten.
- See `docs/crosstalk.md`.

## [1.0.0] — 2026-06-24

### Framework refactor (instrument-neutral)
- Renamed the suite to **STIPS**; split into `stips` (CLI + core) and `obs_stips` (generic LSST glue)
- **Declarative instrument profiles** under `instruments/<name>/` (`profile.py` + camera + hooks), loaded by path via `INSTRUMENT_DIR` — no per-instrument `obs_` package or EUPS product
- Single `-c <config.yaml>` is the sole config source (removed `.env`, `-p/--profile`, and `os.environ` fallbacks)
- Profile-driven collection prefix, skymap name/geometry, filters, header translation, ISR overrides, `boresight_rotation_angle`, and `fetch_data`
- Generic reference pipelines/configs shipped from `obs_stips/instrument_defaults/` with an instrument-dir-first resolver

### CTIO 1.0m / Y4KCam — second instrument
- First **multi-amplifier** camera (4-amp, central-cross overscan); measured per-amp gains; amp-flip + parallel-overscan ISR fixes (seam-free assembly)
- **On-chip binning** support (`CCD_BINNING`): one profile reduces unbinned 4064² and 2×2-binned 2072² raws (imaging scales, overscan fixed)
- **NOIRLab Astro Data Archive** `fetch_data` hook (funpack + integer-`FILTER` normalization)
- Astrometry fix: profile `boresight_rotation_angle=180°` (Y4KCam mounted rotated) — median residual 13.5″ → 0.12″
- Validated end-to-end: unbinned 2007 PG1047 (sub-arcsec astrometry, ~46 mmag photometry) and 2×2-binned 2011 B/V/R/I standard fields (0.578″/px, sub-arcsec V/R/I)

### Extended Objects & Narrowband Filters

- Per-filter narrowband isolation for Halpha, [OIII], g', r' filters
- Per-band-group processing (broadband and narrowband processed separately)
- 12-night extended objects survey configuration (2023B-2025B)
- 9 supported filters: B, V, R, I, g', r', Halpha, [OIII], clear

## [0.1.0] — 2026-03-03

### Exoplanet Transit Detection
- First exoplanet transit detection with the Nickel 1-meter telescope
- HD 189733 b detected at 13-sigma from 400 B-band exposures (4s cadence)
- LSST-native `DifferentialPhotTask` for ensemble differential aperture photometry
- BLS transit search module with configurable period/duration grids

### Variable Star Period Recovery
- Lomb-Scargle period analysis module for pulsating variables
- CY Aqr, DY Peg, AC And periods recovered from single-night V-band observations
- Example variable star campaign templates

### BPS / HPC Integration
- Full pipeline validated end-to-end through BPS, Parsl, and Slurm
- Docker Slurm test cluster (AlmaLinux 9, Slurm 22.05)
- Singularity `.def` for HPC deployment
- Conditional `--qgraph-datastore-records` for BPS vs. local execution

### Supernova Lightcurves
- SN 2023ixf (Type IIP): 22-night monitoring campaign, classic plateau lightcurve
- SN 2020wnt (SLSN-I): multi-epoch detections at z=0.032
- PS1 and Nickel coadd template strategies for DIA
- Configurable lightcurve display: apparent/absolute mag, flux, days-since-explosion

### Pipeline Architecture
- YAML-driven full pipeline orchestration (`nickel run`)
- Four-tier calibrateImage fallback chain (99.4% science processing success)
- Per-band DIA and forced photometry for partial-failure resilience
- Degenerate WCS detection and exclusion for coadd templates
- FastAPI real-time monitoring dashboard

### Infrastructure
- `nickel` CLI with 16 commands covering the full pipeline lifecycle
- Profile-based configuration system for multi-target campaigns
- CI with LSST Science Pipelines container, pre-commit, and ruff/black
- Docker images published to GHCR (`stips`, `stips-slurm`, `stips-hpc`)

## [0.0.1] — 2025-06-08

- Initial commit: obs_nickel instrument package (camera geometry, translator, ISR)
- NickelTranslator for FITS header metadata extraction
- Single-CCD detector layout, visit_system ONE_TO_ONE
- Basic test suite for instrument registration and raw ingestion
