# Changelog

All notable changes to the Nickel Processing Suite are documented here.

## [Unreleased] — Extended Objects & Narrowband Filters

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
- Docker images published to GHCR (`nps`, `nps-slurm`, `nps-hpc`)

## [0.0.1] — 2025-06-08

- Initial commit: obs_nickel instrument package (camera geometry, translator, ISR)
- NickelTranslator for FITS header metadata extraction
- Single-CCD detector layout, visit_system ONE_TO_ONE
- Basic test suite for instrument registration and raw ingestion
