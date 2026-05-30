# AAS 246 STIPS iPoster — Panel Copy

Final text for each panel. Word budgets per spec §7.

## Panel 1 (~60-80 words)

One-meter class telescopes have accumulated decades of archival imaging and remain the most accessible workhorses for amateurs and professionals alike. What they lack is an actively maintained, modern reduction pipeline that keeps pace with survey-grade software. STIPS — the Small Telescope Imaging Pipeline System — closes that gap by wrapping the LSST Science Pipelines for the 1-m class, bringing calibration, difference imaging, forced photometry, and lightcurve extraction to small-telescope data.

## Panel 2 (~40 words caption)

STIPS provides a thin small-telescope abstraction layer over the LSST Science Pipelines: instrument plugins handle telescope-specific concerns, while a YAML+CLI front-end drives end-to-end processing — calibration, difference imaging, forced photometry, and lightcurves — from raw frames to science-ready products.

## Panel 3 (~70 words)

Validated against Landolt with 76 measurements across 10 standards spanning the full Landolt color range (B−V from −0.19 to +1.74). R-band residual: −0.005 ± 0.062 mag. I-band residual: −0.038 ± 0.062 mag. B-band color-term slope: +0.080 mag/(B−V). V-band color-term slope: +0.099 mag/(B−V). Method: cross-match `single_visit_star` against Landolt; apply `initial_photoCalib_detector`; convert AB→Vega per Blanton & Roweis 2007.

## Panel 4 (~60 words)

STIPS was cross-validated against public ZTF (ALeRCE) photometry on two well-observed transients. SN 2023ixf: 141 Nickel R/I points spanning days 1.4–75.5 post-explosion. SN 2020wnt: 65 Nickel R/I points covering peak through late decline. Both campaigns agree with ZTF at the sub-tenth-magnitude level near peak, and the Nickel coverage extends past ZTF's late-time baseline for SN 2023ixf.

## Panel 5 — two subsections (~40 words each)

### Multi-instrument

The same architecture has been extended to CTIO 0.9m via the `InstrumentPlugin` system (Phase 1 + 2 implementation complete on `feature/obs-smalltel-phase1`; full DRP integration in progress). Single ISR validation passed.

### Multi-platform

The same STIPS code runs locally, in Docker, or on Slurm clusters via BPS/Parsl. End-to-end validated on a 22-night concurrent test through the Docker+Slurm cluster — identical inputs, identical outputs, no per-platform code paths.

## Panel 6 — four subtiles (~25 words each)

### Transients

SN 2023ixf early plateau in R/I (days 1.4–75.5). Difference-image forced photometry tracks the plateau magnitude across the campaign and into the late-time decline.

### Exoplanets

HD 189733 b transit detected at >10σ from differential aperture photometry on ~400 B-band 4-second exposures from a single night.

### Variable stars

CY Aqr V-band period detected from a single night of 47 measurements; phase-folded at the known fundamental period 0.061 d.

### Extended objects

Narrowband (Hα, [O III]) and Sloan (g', r') workflows supported for galaxies, H II regions, and planetary nebulae.

## Panel 7

- GitHub: `github.com/danpgause/stips`
- Install: `uv pip install -e packages/data_tools`
- Contact: Dan Gause, NRAO — `<email placeholder>` · ORCID: `<orcid placeholder>`

## Credits / attributions

Logos and any free-use images sourced for the poster:

- NRAO logo — source: https://info.nrao.edu/nrao-brand/logo-1 (file: http://www.nrao.edu/icons/nrao_logo_pms_300.png). License: NRAO brand assets, free for scientific/educational use per the NRAO Style Guide (https://info.nrao.edu/nrao-brand/NRAOStyleGuide.pdf). Credit: NRAO/AUI/NSF.
- Lick Observatory logo — source: https://www.lickobservatory.org/ (file: https://bpb-us-w2.wpmucdn.com/science.ucsc.edu/dist/6/11/files/2021/04/New-Lick-Logo-White-Dome-Yellow-transparent.png). License: official UC Observatories / Lick Observatory mark; use with attribution. Credit: UC Observatories / Lick Observatory. For formal permission contact media@ucolick.org.
- LSST / Rubin Observatory logo — source: https://noirlab.edu/public/products/logos/logo064/ (file: https://noirlab.edu/public/media/archives/logos/original_trans/logo064.png). License: Creative Commons Attribution 4.0 International (CC BY 4.0), per https://noirlab.edu/public/copyright/. Credit: Rubin Observatory/NSF/AURA.
- CTIO 0.9m photo — source: https://noirlab.edu/public/images/img20221221_12114077-CC/ ("CTIO History — Snow on Cerro Tololo", showing the SMARTS 0.9-m and Curtis Schmidt domes; file: https://storage.noirlab.edu/media/archives/images/large/img20221221_12114077-CC.jpg, converted to PNG). License: CC BY 4.0 per https://noirlab.edu/public/copyright/. Credit: CTIO/NOIRLab/NSF/AURA/R. González.
- Docker logo — source: https://www.docker.com/company/newsroom/media-resources/ (file: https://www.docker.com/static/Docker-Logos-1.zip, asset `docker-logo-ocean-blue.png`). License: Docker brand assets, used per Docker Trademark Guidelines (https://www.docker.com/legal/trademark-guidelines/). Credit: Docker, Inc.
- Slurm — referenced as styled text only (no logo image). The "Slurm" name is a SchedMD trademark; SchedMD does not publish an official brand kit, so we avoid embedding any logo image to sidestep trademark/copyright ambiguity.
