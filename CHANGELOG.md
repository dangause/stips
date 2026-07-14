# Changelog

All notable changes to STIPS (the Small Telescope Image Processing Suite) are documented here.

## [2.0.1] — 2026-07-14

### Fixed
- Singularity release publication works end-to-end: fuse build deps on current
  runners, v-less image tag, ORAS publication to `ghcr.io/<owner>/stips-sif`
  (the 3.2 GB .sif exceeds GitHub's 2 GiB release-asset cap), `registry login`
  for Singularity 4.x, and `packages: write` job permissions. A
  `test-singularity` PR label runs the publish end-to-end inside a PR.
- `make test` stack harness: `packages/refcats/src` was missing from
  PYTHONPATH (refcats tests could not import outside with-stack.sh).

### Changed
- Shared exec tooling (Makefile, with-stack.sh, bootstrap, docker images, BPS
  sites) discovers instrument data packages generically under
  `$INSTRUMENT_DIR` (any `ups/`-bearing subdir) instead of hardcoding
  `obs_nickel_data`/`testdata_nickel`; retired stale `obs_nickel` references
  (CI step name, fitter guidance strings, test mock paths).

## [2.0.0] — 2026-07-14

A large documentation-and-correctness audit campaign. The grouped summary below
is at user level; the finding-tagged subsections that follow it keep the detailed
per-area notes.

### Added
- **Generic calibration tooling** as console scripts, so a fork produces its own
  fitted assets instead of copying Nickel's: `stips-defects-build` (defect maps
  from master calibs), `stips-colorterms-fit` (Landolt-fit color terms), and
  `stips-tune-calibrate-image` (searches `calibrateImage` parameters to produce
  `tuned_configs/`). Recipes under `instruments/nickel/{defects,colorterms,tuning}/README.md`.
- **`stips measure-crosstalk`** and declarative `CrosstalkSpec` for multi-amp
  cameras (detailed below).
- **Shared framework modules** a fork builds on: `stips.fetch`
  (`make_fetch_data` wrapper + `parse_night`; a fork's `fetch.py` implements only
  `_fetch_night` + `build_kwargs`), `stips.make_exposure_id` (the reference
  31-bit-safe exposure-id scheme), `stips.testing.instrument_contract` (the
  auto-discovered contract-test harness — see `docs/instrument-contract.md`),
  `core/dataset_types.py` (central Butler dataset-type constants, pinned by a
  contract test), `core/download.py` (download orchestration), `core/query.py`
  (a Butler string-literal sanitizer), and `core/pipeline.PipetaskStage` (shared
  pipetask/butler choreography).
- **Profile `ps1_band_map`** — declares which local science bands are
  PS1-template eligible and the PS1 band each maps to (drives `template.type: auto`).
- **New docs**: `docs/stack-bump-runbook.md`, `docs/instrument-contract.md`,
  `docs/migrations.md`, and `packages/obs_stips/instrument_defaults/README.md`
  (the tiering contract).

### Changed
- **Packaging is framework-only.** `packages/` now holds just `stips`,
  `obs_stips`, and `refcats`; **all** Nickel assets moved under
  `instruments/nickel/` (`obs_nickel_data`, `testdata`, `defects/`,
  `colorterms/`, `tuning/`, and the vendored `lick_searchable_archive`, marked
  with a `VENDORED.md`).
- **`refcats` is now the `stips-refcats` distribution** (import `stips_refcats`);
  the old `nickel_refcats` import remains as a thin re-export shim.
- **`obs_data_package` resolution precedence** clarified: `package_dir` overrides
  the location; otherwise STIPS looks under `<INSTRUMENT_DIR>/<obs_data_package>`
  first, then the reference `packages/<name>` layout.
- **CLI handlers thinned** — they delegate to core modules: `download`
  orchestration lives in `core/download.py`, `clean` is a plan/execute flow,
  lightcurve display options flow only through `LightcurveConfig`, and
  `dashboard` requires and threads the `-c` config.
- **Ops**: the scheduled stack canary runs the pipeline graph-build tests so
  config-field breakage surfaces before the pin moves; CI validates pushes on the
  active development branches. Supported release `v30_0_3`, CI weekly pinned at
  `w_2025_32` (see `docs/stack-bump-runbook.md`).

### Fixed
- **Calibs success is verified against products**, not just the pipetask exit
  code — a run that exits 0 but writes no bias/flat is now reported as a failure
  (or partial), not a success.
- **DIA and forced photometry query both UT `day_obs` values** a local observing
  night can span (pre-/post-midnight), so exposures near UT midnight are no
  longer silently dropped.
- **Coadd template rebuild is build-then-swap** (F-009): a rebuild writes to a
  fresh RUN and the parent chain is repointed only on success, so a failed
  rebuild can't leave a half-built template in place.
- **Provenance records the true LSST *pipelines* (EUPS) version and the profile's
  instrument**, distinct from the conda/rubin-env name.
- **`filter_map.py` covers CTIO 1.0m's uppercase `U`** physical filter
  (previously a live KeyError for analysis tasks on U-band data).

### Deprecated
- The `nickel_refcats` import path — use `stips_refcats`; importing it emits a
  `DeprecationWarning`.
- The `nights: {YYYYMMDD: {band: [...]}}` mapping form in run configs — only its
  night keys are read now; use the `science: nights: [...]` list.

### Migration notes
- **QA task labels renamed `...Nickel` → `...Visit`** (F-013): task labels become
  Butler dataset-type names, so dashboards/queries referencing the old
  `...Nickel_metadata`/`_log`/`_config` names must update. No data loss and
  nothing to migrate on disk. See `docs/migrations.md`.

### E2E validation fixes
End-to-end runs on real Nickel and CTIO/Y4KCam data hardened the venv/stack
boundary and the forking path:
- **Refcat fetch runs from a plain venv.** The HTM cone-coverage math and
  `convertReferenceCatalog` now fall back to in-stack execution automatically, so
  `stips run` with `refcat.mode: gaia_ps1` works without a stack-activated shell
  (previously it only ran from inside the stack).
- **`stips-refcats` declares its fetch dependencies** (`astroquery`, `astropy`,
  `numpy`, `pandas`), so a clean `uv sync --group dev` can fetch Gaia/PS1.
- **A failed refcat ensure aborts `stips run` early** with the root cause, instead
  of warning and limping into science where every night died with an opaque
  `MissingDatasetTypeError('panstarrs1_dr2')`.
- **Instruments with no tuned `calibrateImage` config now run science** on a
  neutral schema-compatibility default (measurement plugins/radii/slots only, no
  instrument tuning) — a fork no longer needs to fit `calibrateImage` before
  processing. An explicitly-configured-but-missing config path still errors (typo
  protection).
- **gaia_ps1 mode now covers the stage-1 QA ref-match tasks** via two neutral
  overlays (`refcats_gaia_ps1_qa_astrom.py`, `refcats_gaia_ps1_qa_photom.py`), so
  fields outside local MONSTER shard coverage no longer fail quantum-graph
  construction.
- **Instrument config overrides no longer import the profile.** The PS1 band map
  reaches the `refcats_gaia_ps1*.py` overlays through the new `STIPS_PS1_BAND_MAP`
  env var (exported by `run_with_stack`), fixing saved-quantum-graph replay, which
  re-imports every module a pex_config file touched during config exec.
- **PS1 templates must exceed the camera FOV plus dither margin.** On a large
  (~20′) FOV like Y4KCam, too small a `template.size` left dithered pointings with
  no PSF-matching kernel candidates (`NoKernelCandidatesError`).
- **Dashboard requires `fastapi>=0.110`** (request-first `TemplateResponse`).

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
