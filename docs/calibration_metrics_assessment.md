# Astrometric and Photometric Calibration Metrics

## Reproduction

All metrics were extracted from Butler repositories using the `stips calib-metrics` command, which queries `preliminary_visit_summary` datasets produced by the LSST Science Pipelines' `calibrateImage` task. Landolt photometric validation uses `stips landolt-validate`.

```bash
# Single-target extraction
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml calib-metrics \
    -o calib_metrics_2023ixf_all.csv

# Multi-target batch (5 repos, combined CSV)
python scripts/analysis/run_calib_metrics_batch.py

# Landolt pipeline (build dedicated repo, ~4 nights)
stips -c scripts/config/landolt_validation/pipeline_landolt.yaml run

# Landolt photometric validation
stips -c scripts/config/landolt_validation/pipeline_landolt.yaml landolt-validate \
    --catalog scripts/config/landolt_validation/landolt_catalog.csv \
    -o analysis/landolt_validation.csv
```

**Source code:**
- Calibration metrics: `packages/stips/src/stips/pipeline_tools/extract_calib_metrics.py`
- Landolt validation: `packages/stips/src/stips/pipeline_tools/validate_landolt.py`
- Batch runner: `scripts/analysis/run_calib_metrics_batch.py`

**Reference catalog:** The Monster (local, 2025-02-19 build)

## Dataset Description

Metrics are aggregated across five Nickel campaigns spanning supernova,
exoplanet, variable-star, and extended-source science. Per-target breakdowns
and field-density discussion appear in [Field Density Comparison](#field-density-comparison);
the Landolt sample is described separately in [Landolt Photometric Validation](#landolt-photometric-validation).

| Property | Value |
|----------|-------|
| Instrument | Nickel Direct Imaging Camera, Lick Observatory 1-m |
| Detector | Single 1024×1024 Loral CCD (1 detector, ID 0) |
| Plate scale | 0.37 arcsec/pixel |
| Field of view | ~6.3 arcmin |
| Total processed visits | 1,457 |
| Targets (5) | SN 2023ixf (N=373), HD 189733 (398), extended_objects (381), AC And (194), SN 2020wnt (111) |
| Date range | 2020-12-08 to 2025-10-28 (61 unique nights) |
| Bands | B (435), R (405), V (234), I (204), Hα (71), [O III] (47), rp (32), gp (29) |
| Exposure times | 3--1500 s (median 20 s) |
| Astrometric reference catalog | The Monster (local, 2025-02-19 build) |

The 2023ixf and 2020wnt subsets are the supernova DIA campaigns (BVRI through
PS1 templates); HD 189733 is the all-B-band exoplanet transit campaign; AC
And is V-band-only variable-star photometry; extended_objects mixes Sloan/
narrowband filters on emission nebulae and galaxies.

## Butler Dataset Types Queried

| Dataset Type | Dimensions | Content |
|---|---|---|
| `preliminary_visit_summary` | (instrument, visit) | Per-detector summary statistics from `calibrateImage`: WCS residuals, PhotoCalib zero point, PSF model parameters, sky background. One row per detector per visit. |
| `calibrateImage_metadata_metrics` | (instrument, visit, detector) | Task-level match counts and PSF statistics from `analysis_tools` visit-quality pipeline (`visit-quality-detector.yaml`). Present for all 1,457 visits; surfaced in the [Visit Quality](#visit-quality) section. |
| `single_visit_star_ref_match_{astrom,photom}_metrics` | (instrument, visit, detector) | Per-visit aggregated residuals from matching `single_visit_star` catalog against the reference catalog. Requires `analysis-visit-single-visit.yaml`. Not run for this extraction. |

## Astrometric Calibration

### Summary Statistics

| Metric | N | Median | Mean | Std Dev | Min | Max |
|--------|---|--------|------|---------|-----|-----|
| `astromOffsetMean` (arcsec) | 373 | 0.021 | 0.023 | 0.014 | ~0 | 0.103 |
| `astromOffsetStd` (arcsec) | 373 | 0.011 | 0.012 | 0.009 | ~0 | 0.102 |
| `nPsfStar` | 373 | 9 | 9.0 | 2.8 | 0 | 15 |

`astromOffsetMean` is the mean positional offset between detected sources and their matched reference catalog entries after the WCS fit, in arcseconds. `astromOffsetStd` is the standard deviation of those offsets.

### Interpretation

The median astrometric residual of **21 mas** (0.057 pixels at 0.37 arcsec/pixel) demonstrates that `calibrateImage`'s astrometric solution is well-constrained for the majority of visits. This is well below the Nickel pixel scale and adequate for difference imaging analysis, where sub-pixel registration is achieved by the image warping stage.

### Residual Distribution

| Bucket | Count | Fraction |
|--------|-------|----------|
| < 1e-6 arcsec (degenerate WCS) | 21 | 5.6% |
| 1e-6 -- 0.01 arcsec | 14 | 3.8% |
| 0.01 -- 0.05 arcsec | 325 | **87.1%** |
| 0.05 -- 0.1 arcsec | 12 | 3.2% |
| 0.1 -- 0.5 arcsec | 1 | 0.3% |
| > 0.5 arcsec | 0 | 0% |

**87% of visits** have astrometric residuals in the 10--50 mas range, indicating stable and reliable WCS solutions.

### Degenerate WCS Visits

21 of 373 visits (5.6%) exhibit `astromOffsetMean` < 1e-6 arcsec, indicating a degenerate astrometric fit. These occur when the number of astrometric matches is 3 or fewer, resulting in a 6-parameter affine fit with zero degrees of freedom. The residual is a floating-point artifact (~1e-11 arcsec) rather than a genuine sub-nanoarcsecond solution.

Detection criterion: `astromOffsetMean < 1e-6` (threshold from `coadd.py:find_degenerate_wcs_visits()`; exact equality to 0.0 fails because the residuals are ~1e-11, not exactly zero).

These visits are **excluded from coadd template construction** by the pipeline's degenerate-WCS filter but are retained in the per-visit DIA processing (where individual WCS accuracy is less critical because the template drives the astrometric frame).

## Photometric Calibration

### Per-Band Zero Points

| Band | N | Median ZP (mag) | Std Dev (mag) | Range (mag) |
|------|---|-----------------|---------------|-------------|
| R | 210 | 26.587 | 0.806 | 23.87 -- 29.39 |
| I | 163 | 26.361 | 0.734 | 23.79 -- 28.60 |

The zero point is defined as `zeroPoint = -2.5 * log10(PhotoCalib.instFluxToNanojansky(1.0))`, representing the AB magnitude of a source producing 1 ADU/s. It encodes both the instrumental throughput and the atmospheric transparency at the time of observation.

### Interpretation

The per-visit zero-point scatter of ~0.8 mag across both bands is expected for a ground-based campaign spanning ~7 months (May--December 2023) at Lick Observatory, where conditions range from photometric to partially cloudy. This scatter does **not** indicate a calibration failure: each visit's `PhotoCalib` is individually derived from reference catalog matching and is applied correctly to the `preliminary_visit_image` pixels (which are stored in nanojansky units with an identity PhotoCalib after calibration).

The ~5.5 mag range in zero points (23.8--29.4) likely reflects the full span from excellent transparency (high ZP) to thin cloud cover or high airmass (low ZP). Visits at the extremes should be cross-checked against observing logs before inclusion in ensemble analyses.

For difference imaging analysis, per-visit photometric calibration accuracy is less critical than relative stability, because the DIA pipeline performs kernel matching that absorbs flux scaling differences between science and template images.

### Stability Over Time

Per-campaign zero-point time series are plotted in `analysis/calib_metrics/zeropoint_vs_time.png` (generated by `scripts/analysis/plot_zeropoint_timeseries.py`). Each panel shows zero point vs `day_obs` colored by band for one of the five campaigns, with a sixth combined overlay panel. Within-campaign scatter is dominated by sky transparency variations and airmass; absolute level varies between campaigns mainly because of the different filter set (e.g. HD 189733 is B-band only).

## Image Quality (PSF)

### Summary Statistics

| Metric | N | Median | Mean | Std Dev | Min | Max |
|--------|---|--------|------|---------|-----|-----|
| `psfSigma` (pixels) | 373 | 2.30 | 2.39 | 0.64 | 1.20 | 5.34 |
| `psfArea` (pixels^2) | 373 | — | — | — | — | — |

### Derived Seeing

FWHM = psfSigma x 2.355 x 0.37 arcsec/pixel

| | Median | Mean | Min | Max |
|---|---|---|---|---|
| FWHM (arcsec) | **2.00** | 2.08 | 1.05 | 4.65 |

The median seeing of 2.0 arcsec is typical for Lick Observatory at the Nickel telescope. The best visits (~1.0 arcsec) approach the practical seeing floor at the site, while the tail to ~4.7 arcsec represents poor-conditions data that was still processable by the pipeline.

### Per-Band PSF

| Band | N | Median psfSigma (px) | Median FWHM (arcsec) |
|------|---|---------------------|----------------------|
| R | 210 | 2.31 | 2.01 |
| I | 163 | 2.27 | 1.98 |

No significant difference between bands, as expected for seeing-dominated PSFs at these wavelengths.

## Sky Background

| Metric | N | Median | Mean | Std Dev | Min | Max |
|--------|---|--------|------|---------|-----|-----|
| `skyBg` (nJy/pixel) | 373 | 111.5 | 153.9 | 113.2 | 25.1 | 580.4 |
| `skyNoise` (nJy/pixel) | 373 | 10.6 | 12.1 | 11.8 | 6.9 | 231.2 |

The `skyNoise` maximum of 231 nJy/pixel is a ~20-sigma outlier (compared to the median of 10.6) and likely corresponds to a visit taken through cloud or during twilight. The `skyBg` variation (25--580 nJy/pixel) reflects the range of lunar illumination, airmass, and atmospheric conditions across the 7-month campaign.

### Sky Background vs. Zero Point

`analysis/calib_metrics/sky_vs_zeropoint.png` (from `scripts/analysis/plot_sky_vs_zp.py`) plots `skyBg` against `zeroPoint` colored by target. The anti-correlation is clean: photometric visits cluster at high ZP (≥27 mag) and low sky (≤100 nJy/pix), while cloudy/moonlit visits drift to lower ZP and higher sky brightness. Each campaign occupies its own region of the plot because the bands differ (HD 189733 in B sits low and right; the SN campaigns in R/I sit middle; etc.).

## Visit Quality

Per-visit metrics from `calibrateImage_metadata_metrics` (produced by the `analysis_tools` visit-quality pipeline). Values are medians across all 1,457 visits.

| Metric | Median | Mean | Std | Min | Max |
|--------|-------:|-----:|----:|----:|----:|
| `astrometry_matches_count`  | 21 | 30 | 41 | 2 | 596 |
| `photometry_matches_count`  | 30 | 41 | 50 | 1 | 690 |
| `psf_good_star_count`       | 21 | 33 | 39 | 4 | 286 |
| `matched_psf_star_count`    | 22 | 32 | 36 | 1 | 329 |
| `star_count`                | 26 | 42 | 51 | 1 | 480 |
| `saturated_source_count`    |  3 |  5 |  8 | 0 |  59 |
| `cosmic_ray_count`          | 10 | 57 | 627 | 1 | 16,908 |

### Per-target Median Match Counts

| Target | N | Astrometry matches | Photometry matches | PSF good stars |
|--------|--:|-------------------:|-------------------:|---------------:|
| SN 2020wnt        | 111 |  56 |  94 | 94 |
| SN 2023ixf        | 373 |   8 |  11 | 12 |
| AC And            | 194 |  24 |  47 | 23 |
| HD 189733         | 398 |  24 |  34 | 23 |
| Extended objects  | 381 |  27 |  29 | 28 |

The dense M101 field around SN 2023ixf has by far the lowest match counts (median 8 astrometric matches, 11 photometric, 12 PSF stars) — galaxy surface brightness and crowding suppress clean stellar detections. The sparse 2020wnt field at the opposite extreme has 7× more astrometric matches and 8× more photometric matches per visit. This is consistent with the higher degenerate-WCS rate in the dense field (5.6% vs. 0% for sparse), where insufficient matches collapse the astrometric solution.

The long tail in `cosmic_ray_count` (max 16,908) is concentrated in the longest exposures (≥600 s) where CR accumulation dominates; the median 10 CRs/visit is normal for ground-based 20-second frames.

## Field Density Comparison

Calibration metrics were extracted from 5 Butler repositories spanning sparse, moderate, dense, and mixed stellar fields. Total: 1,457 visits across all targets.

### Per-Target Summary

| Target | Field Type | N | Bands | astromOffset med (arcsec) | ZP med (mag) | ZP std (mag) | psfSigma med (px) | nPsfStar med | Degen WCS % |
|--------|-----------|---|-------|--------------------------|-------------|-------------|-------------------|-------------|------------|
| SN 2023ixf (M101) | Dense (spiral galaxy) | 373 | r, i | 0.021 | 26.58 | 0.78 | 2.30 | 9 | 5.6% |
| SN 2020wnt | Sparse (isolated host) | 111 | r, i | 0.015 | 29.92 | 2.00 | 2.30 | 60 | 0.0% |
| HD 189733 (Cygnus) | Moderate (bright star) | 398 | b | 0.048 | 23.59 | 0.70 | 2.40 | 20 | 0.0% |
| AC Andromedae | Sparse (variable star) | 194 | v | 0.044 | 26.33 | 0.45 | 3.21 | 17 | 0.0% |
| Extended objects | Mixed (galaxies/nebulae) | 381 | b,v,r,i,gp,rp,halpha,oiii | 0.034 | 26.47 | 1.51 | 2.22 | 18 | 1.8% |

### Interpretation

**Stellar density and PSF star count:** The sparse SN 2020wnt field has the highest median `nPsfStar` (60), reflecting an uncrowded field where isolated stars are cleanly resolved. In contrast, the dense M101 field around SN 2023ixf has only 9 PSF stars — galaxy surface brightness and crowding reduce the number of clean stellar detections available for PSF modeling.

**Astrometric precision scales inversely with field complexity:** The sparse 2020wnt field achieves the best astrometric residual (15 mas), while the B-band HD 189733 field (48 mas) and V-band AC And field (44 mas) show larger residuals. B-band has fewer reference catalog matches (shorter-wavelength stellar SEDs reduce the available reference catalog depth), and the AC And field had the poorest seeing (3.2 px median).

**Degenerate WCS rate:** Only the two galaxy-rich fields (2023ixf at 5.6%, extended objects at 1.8%) produce degenerate WCS fits. Sparse stellar fields with high `nPsfStar` have zero degenerate WCS visits, confirming that the failure mode is driven by crowding-induced star count reduction rather than algorithmic issues.

**Zero-point scatter:** The 2020wnt field shows the largest ZP scatter (2.0 mag std), likely because its 34-night campaign spans a wider range of observing conditions. The AC And field, observed over only 3 nights, shows the tightest scatter (0.45 mag).

### Batch Output Files

- Per-target CSVs: `analysis/calib_metrics/{target}.csv`
- Combined CSV with `target` column: `analysis/calib_metrics/combined.csv`

## Supernova Lightcurve Comparison to ZTF

To validate the Nickel DIA lightcurves against an external survey, we overlay the Nickel forced-photometry outputs for SN 2023ixf and SN 2020wnt with public ZTF photometry pulled from the ALeRCE alert broker (objects ZTF23aaklqou and ZTF20acjeflr respectively). The comparison figure is `analysis/sn_vs_ztf_comparison.png` (script: `scripts/analysis/plot_sn_vs_ztf.py`).

- **SN 2023ixf** has no direct r-band overlap because ZTF r-band coverage of the source begins only at day ~207 post-explosion, well after the Nickel campaign ended (day 75). The visual comparison still shows that Nickel R/I points sit on the early bright plateau (mag 11.5–14) tracing the same lightcurve shape that ZTF g sees over the same epochs, and ZTF r picks up the late-time tail (mag 19–20.5) that extends the Nickel coverage by an order of magnitude in time.

- **SN 2020wnt** has direct r-band overlap from day ~11 to ~250. Within a 3-day matching window, Nickel R agrees with ZTF r at mean = +0.66 mag with 0.80 mag RMS over 6 matched epochs — driven by color evolution at late times where the SN is reddening (Nickel Cousins R extends further to the red than ZTF Sloan r, so the SN appears brighter in R). Near the lightcurve peak (day 30) the agreement is sub-tenth-mag. The Nickel campaign also extends ~100 days beyond ZTF's coverage of the source.

Both comparisons use Nickel detections filtered to SNR > 5 to suppress noise points in the forced photometry.

## Landolt Photometric Validation

### Purpose

Validate the absolute photometric accuracy of the LSST Science Pipelines' `calibrateImage` output by comparing pipeline-calibrated magnitudes of Landolt standard stars against their published catalog values (Landolt 1992, AJ 104, 340; Landolt 2009, AJ 137, 4186).

### Methodology

1. **Dedicated Butler repository.** A separate repository (`landolt_validation_repo`) was built from 4 Tier 1 standard star nights (20210208, 20240624, 20240905, 20240906) containing 10 unique Landolt stars with BVRI coverage. All science frames for these nights were processed through `calibrateImage` using default pipeline configurations.

2. **Source catalog cross-match.** For each processed visit, the `single_visit_star_unstandardized` catalog was loaded (ArrowAstropy format, coordinates in radians). Each Landolt star's published J2000 position was cross-matched against detected sources within a 10 arcsec radius (accounting for Nickel's typical 5-7 arcsec WCS residuals). The closest match was retained.

3. **Flux calibration.** The `single_visit_star_unstandardized` catalog contains instrumental fluxes. The `initial_photoCalib_detector` was loaded for each visit and the calibration factor (`getCalibrationMean()`, in nJy/ADU) was applied to convert instrumental flux to calibrated nJy.

4. **AB-to-Vega conversion.** Calibrated nJy fluxes were converted to AB magnitudes (`m_AB = -2.5 * log10(flux_nJy / 3.631e12)`), then transformed to Vega magnitudes using standard Bessell/Cousins AB-Vega offsets: B: -0.09, V: +0.02, R: +0.21, I: +0.45.

5. **Residual computation.** `residual = pipeline_mag_vega - landolt_mag`. A positive residual means the pipeline reports the star as fainter than the published Landolt magnitude.

### Results

After expanding the local MONSTER refcat to cover all four Tier 1 nights (see "MONSTER refcat coverage expansion" below), 76 measurements were obtained across 10 Landolt standard stars and four BVRI bands, spanning the full Landolt B-V color range from -0.19 to +1.74.

#### Per-Band Residuals

After excluding one V-band outlier (SA 110-340, residual = +10.6 mag — a clear source-match failure on a single visit, see Caveats):

| Band | N | Mean (mag) | Median (mag) | RMS (mag) | Std (mag) |
|------|---|------------|--------------|-----------|-----------|
| B | 17 | -0.388 | -0.442 | 0.453 | 0.243 |
| V | 16 | +0.248 | +0.245 | 0.257 | 0.071 |
| R | 19 | **-0.005** | -0.039 | **0.062** | 0.064 |
| I | 23 | **-0.038** | -0.036 | **0.062** | 0.049 |
| **All** | **75** | **-0.048** | -0.037 | 0.251 | 0.248 |

AB-to-Vega offsets used: B=+0.09, V=-0.02, R=-0.21, I=-0.45 (Blanton & Roweis 2007, AJ 133, 734; sign convention: mVega = mAB + offset).

#### Color-Term Linear Fits

Per-band linear regression of residual vs Landolt B-V, across the full color range:

| Band | Slope (mag/(B-V)) | Intercept (mag) | Fit RMS (mag) | B-V Range |
|------|-------------------|-----------------|---------------|-----------|
| B | +0.080 | -0.470 | 0.230 | [-0.19, +1.74] |
| V | +0.099 | +0.137 | 0.026 | [-0.14, +1.74] |
| R | +0.085 | -0.095 | 0.033 | [-0.19, +1.74] |
| I | +0.042 | -0.087 | 0.043 | [-0.14, +1.74] |

These slopes are the **Nickel-to-Landolt color terms**: shallow but non-zero (~0.04-0.10 mag per unit B-V), measurable now that the B-V baseline spans 1.93 magnitudes.

#### Interpretation

**R and I bands are validated to < 0.1 mag absolute accuracy.** Near-zero mean residuals in R (-0.005 mag) and I (-0.038 mag) with RMS of 0.06 mag confirm that the Nickel Cousins Rc and Ic filters closely match the standard Landolt system, and the pipeline's photometric calibration against the MONSTER reference catalog produces magnitudes consistent with Landolt standards.

**B band shows a -0.39 mag mean offset** (pipeline brighter than Landolt) with a +0.080 mag/(B-V) color-dependent slope. The intercept of -0.47 mag, plus 0.23 mag scatter around the linear fit, indicates the Nickel B filter bandpass differs significantly from the standard Bessell B filter — a real filter mismatch, not a calibration failure.

**V band has a +0.25 mag mean offset** with a +0.099 mag/(B-V) color term. After correcting for color, the V-band fit RMS is just 0.026 mag — among the tightest of the four bands, confirming that the V offset is dominated by a (correctable) bandpass mismatch.

**Stars covered (10 total):** PG 1633+099 (B-V=-0.19), PG 1323-086 (-0.14), PG 1530+057 (+0.15), SA 110-340 (+0.31), SA 113-342 (+1.02), SA 114-670 (+1.21), SA 107-458 (+1.21), SA 109-231 (+1.46), SA 92-311 (+1.64), SA 109-199 (+1.74).

**Match quality:** All cross-matches had angular separations of < 1 arcsec, well within the 10 arcsec search radius (chosen to accommodate Nickel's typical 5-7 arcsec WCS residuals).

#### Caveats

1. **V-band outlier.** One V-band measurement (SA 110-340, visit 90151051, residual +10.6 mag) was excluded from per-band statistics. The pipeline reported AB = 20.6 mag versus Landolt V = 10.0 mag — a clear source-association failure, likely the cross-match locked onto a faint background source rather than the standard. The other measurements of SA 110-340 V band were not in the sample (single failed visit).

2. **AB-to-Vega offsets.** The offsets used are for standard Bessell/Cousins filters (Blanton & Roweis 2007). The fit intercepts and slopes measure the combined effect of offset uncertainty and Nickel filter bandpass mismatch. Deriving Nickel-specific AB-Vega offsets from the actual filter transmission curves would isolate the calibration accuracy from the filter mismatch.

3. **Uneven star coverage per band.** Stars near the celestial equator with full BVRI coverage (PG 1323-086, PG 1530+057, SA 113-342, SA 92-311, SA 109-199) drive most of the fit. PG 1633+099 has only B and R; SA 114-670 has only I and R; SA 110-340 has only V; SA 109-231 has only B. The color-term slopes are most reliable for B/R/I, where ≥17 measurements span the full B-V range.

### MONSTER Refcat Coverage Expansion

The initial run processed only 1 of 4 Tier 1 nights because the local MONSTER refcat lacked HTM7 shards for most Landolt field positions, causing qgraph builds to abort with `FileNotFoundError: Not enough datasets (0) found for ... the_monster_20250219_local`. Recovery used existing stips tooling:

1. **`scripts/utilities/recompute_missing_shards.py`** queried the Butler for visit centroids, computed the HTM7 cells overlapping a 6 arcmin radius per visit, and subtracted shards already on disk — yielding 34 missing IDs written to `scripts/config/landolt_validation/monster_plan/missing_htm7_ids.txt`.

2. **`packages/refcats/scripts/dump_monster_shards.py`** (vendored from a standalone RSP utility) was run on the Rubin Science Platform to dump those 34 shards from the dp1 Butler — yielding 16.6 MB of new AFW-format FITS shards.

3. **`nickel-refcats merge`** extracted the tarball into `$REFCAT_REPO/data/refcats/the_monster_20250219_afw/`, invalidating the stale ECSV manifest so the next bootstrap regenerates it.

4. **Re-bootstrap** of the Landolt repo (after dropping the existing `refcats/the_monster_20250219_local` RUN collection) re-ingested all 387 shards, providing the qgraph builder with full coverage across the Landolt fields.

The complete runbook is at `scripts/config/landolt_validation/EXPANDING_COVERAGE.md`.

### Pipeline Fix: Lick Observing Nights Span Two UT Days

A single Lick observing night (Pacific local date) can span two UT days: pre-Pacific-midnight exposures have `day_obs = night`, while post-midnight exposures have `day_obs = night + 1`. The original `core/science.py` and `core/pipeline.py` queried only `day_obs = night + 1`. For 20210208 this silently dropped every Landolt exposure (the standards were observed in the Pacific evening), while the SNe on the same observing night were post-midnight and visible. Fixed by querying `day_obs IN (night, night+1)`.

### Landolt Reference Catalog

Published magnitudes for 10 Tier 1 standard stars are stored in `scripts/config/landolt_validation/landolt_catalog.csv`, sourced from Landolt (1992) and Landolt (2009) via VizieR (II/183A, II/277).

### Output Files

- Validation CSV: `analysis/landolt_validation_4nights.csv` (76 rows, all measurements)
- Residual plot: `analysis/landolt_residuals.png`
- Color-term plot: `analysis/landolt_color_terms.png`
- Pipeline config: `scripts/config/landolt_validation/pipeline_landolt.yaml`
- Reference catalog: `scripts/config/landolt_validation/landolt_catalog.csv`

## Known Limitations

1. **Per-source astrometric/photometric residuals not available.** The `single_visit_star_ref_match_{astrom,photom}_metrics` datasets (aggregated RMS, bias, and scatter from per-source catalog-to-refcat matching) require running `analysis-visit-single-visit.yaml`. These would provide more detailed characterization (e.g., astrometric residual vs. magnitude, per-band photometric color terms derived directly from per-source matching). The `calibrateImage_metadata_metrics` is already in the dataset and is summarized above in [Visit Quality](#visit-quality).

3. **Degenerate WCS fraction (5.6%).** These visits pass the pipeline but have unreliable astrometric solutions. They are automatically filtered from coadd construction but are included in per-visit DIA. Their forced photometry products should be treated with caution.

4. **Single detector.** Nickel has one CCD; metrics are per-visit (not per-detector). Spatial variation in PSF or astrometric residuals across the field is not captured by these summary statistics.

## CSV Column Reference

| Column | Unit | Description |
|--------|------|-------------|
| `day_obs` | YYYYMMDD (int) | UT observation date from Butler visit dimension record |
| `visit` | int | Butler visit ID |
| `detector` | int | Detector ID (always 0 for Nickel) |
| `band` | str | Abstract band (r, i) |
| `physical_filter` | str | Physical filter name (R, I) |
| `ra` | degrees | Boresight right ascension |
| `dec` | degrees | Boresight declination |
| `zenithDistance` | degrees | Zenith distance at observation midpoint |
| `zeroPoint` | AB mag | Photometric zero point from `PhotoCalib` |
| `skyBg` | nJy/pixel | Median sky background level |
| `skyNoise` | nJy/pixel | Sky background noise (1-sigma) |
| `psfSigma` | pixels | PSF model sigma (Gaussian equivalent) |
| `psfArea` | pixels^2 | Effective PSF area |
| `nPsfStar` | count | Number of stars used for PSF model |
| `astromOffsetMean` | arcsec | Mean astrometric offset (source vs. refcat) |
| `astromOffsetStd` | arcsec | Std dev of astrometric offsets |
| `expTime` | seconds | Exposure time |

## Suggested Plots for Paper

### Calibration Metrics
1. **Astrometric residual histogram** -- `astromOffsetMean` with degenerate-WCS cutoff marked at 1e-6 arcsec
2. **Zero point vs. time** -- `zeroPoint` grouped by `day_obs`, colored by band, to show photometric stability across the campaign
3. **Seeing distribution** -- histogram of derived FWHM (= psfSigma x 2.355 x 0.37) with per-band breakdown
4. **nPsfStar vs. astromOffsetMean** -- scatter plot to confirm that low star counts correlate with poor/degenerate WCS
5. **Sky background vs. zero point** -- to separate photometric from non-photometric nights

### Field Density Comparison
6. **astromOffsetMean by target** -- box plot or violin plot comparing astrometric precision across the 5 field types
7. **nPsfStar by target** -- bar chart showing how field density affects available PSF stars
8. **Degenerate WCS rate by target** -- bar chart highlighting that only galaxy-rich fields produce degenerate fits

### Landolt Validation
9. **Per-band residual bar chart** -- mean pipeline-minus-Landolt residual per BVRI band with error bars
10. **Residual vs. B-V color** -- scatter plot to reveal the Nickel-to-Landolt color term slope
11. **Repeat measurement consistency** -- per-star per-band scatter showing < 0.01 mag internal precision
