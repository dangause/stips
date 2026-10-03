# STIPS — Capabilities Panel (poster)

> **Historical snapshot.** This is the panel text as presented, written before the
> v2 framework refactor. It refers to the old `obs_nickel` package and `nickel` CLI,
> which are now the declarative `instruments/nickel/` profile and the `stips` CLI.
> See `docs/architecture.md` for the current design.

**STIPS — the Small Telescope Image Processing Suite**
*Survey-grade reduction for 1-meter telescopes, built on the Rubin/LSST Science Pipelines.*

---

## What STIPS does

**◆ LSST instrument integration**
- First-class `obs_nickel` instrument package (single-CCD camera model, AFW geometry)
- FITS metadata translator + raw formatter; validates pointing against stale headers
- 9 filters (Johnson/Bessell BVRI, g′/r′, Hα, OIII, clear)
- Tuned LSST pipeline configs for small-telescope seeing & sparse fields
- Validated on LSST Pipelines v30 & v11; portable to other 1-m single-CCD instruments

**◆ Data acquisition**
- One-command download from the Lick Observatory archive (rate-limited REST client)
- Auto-ingest into the LSST Butler; observing-night ↔ UT bookkeeping

**◆ Calibration & reference data**
- Nightly bias / flat / defect calibration with partial-failure resilience
- Curated defect masks + a flat-field-based defect-generation toolchain
- Local "MONSTER" reference catalog (astrometry + photometry), HTM7-sharded
- Data-driven, Nickel-specific photometric color terms (robust regression)

**◆ Image processing pipelines**
- Instrument Signature Removal → WCS → photometric calibration (per-frame DRP)
- Deep coadd template building (with degenerate-WCS rejection)
- PS1 external templates: cloud download, nJy pre-calibration, PSF-match, reproject
- Difference imaging (Alard–Lupton) for transient & variable detection
- Forced photometry at arbitrary RA/Dec on visit or difference images

**◆ Time-domain science products**
- Multi-band light-curve extraction (apparent/absolute mag, flux, phase)
- Supernova photometry — Type IIP curve for SN 2023ixf; SN 2020wnt
- Exoplanet transit detection — differential photometry + Box Least Squares
- Variable-star period recovery — Lomb–Scargle + false-alarm probability
- Aperture-flux recovery for bright sources where PSF-fitting under-reports

**◆ Calibration validation & QA**
- Landolt standard-star photometric validation (AB↔Vega, Gaia DR3 PM correction)
- Cross-comparison against published photometry & ZTF/ALeRCE
- Multi-field calibration-metrics database (zeropoints, astrometry, PSF, seeing)
- Publication-ready diagnostic figures + assessment notebooks

**◆ Orchestration & operations**
- Unified `nickel` CLI; profile- and YAML-driven full-pipeline runs
- Robustness: coordinate pre-flight checks, four-tier fallback configs, per-band runs,
  template-overlap detection, cross-night calibration reuse
- Scales laptop → cluster via LSST BPS (Parsl + Slurm); Docker test cluster
- Live web dashboard: run monitoring, log streaming, on-the-fly FITS previews

---

## Built with

Python 3.12 · LSST Science Pipelines · Butler · BPS/Parsl/Slurm · Docker
astropy · numpy · scipy · pandas · scikit-learn · matplotlib · Click · FastAPI

---

## Proven on

SN 2023ixf · SN 2020wnt · HD 189733 b (first Nickel + LSST exoplanet transit, 13σ)
CY Aqr · DY Peg · AC And · Landolt standard fields
~1,400 science visits across 5 fields · 33 observing nights
