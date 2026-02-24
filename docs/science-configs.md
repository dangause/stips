# Science Processing Configuration Guide

This document describes the tuned `calibrateImage` configuration files for science processing on the Nickel 1m telescope at Lick Observatory. These configs control PSF modeling, astrometric calibration, photometric calibration, and aperture correction within the LSST Science Pipelines' `CalibrateImageTask`.

## Overview

Science processing quality depends heavily on field star density and observing conditions. A single configuration cannot optimally handle both star-rich fields at low galactic latitude and star-poor fields at high galactic latitude. We provide four configs organized along two axes:

- **Field density**: dense (>30 usable stars) vs. sparse (<25 usable stars)
- **Strictness**: strict (maximize quality) vs. relaxed (maximize completion rate)

### Config Files

All configs live in `packages/obs_nickel/configs/calibrateImage/tuned_configs/`:

| File | Use Case |
|------|----------|
| `dense_strict.py` | Best quality on star-rich fields with good conditions |
| `dense_relaxed.py` | Fallback for star-rich fields with poor WCS or seeing |
| `sparse_strict.py` | Quality processing on star-poor fields |
| `sparse_relaxed.py` | Last resort for the most challenging frames |

### Inheritance

All four configs inherit from `best_calib_t071.py`, which was derived from Optuna hyperparameter tuning (trial 71). The base config provides measurement plugin setup, aperture radii, and reasonable default values. Each tuned config then overrides specific parameters for its target regime.

### Fallback Chains

The configs are designed for sequential fallback — if one fails, the next is tried:

```
Dense fields:   dense_strict → dense_relaxed → sparse_strict → sparse_relaxed
Sparse fields:  sparse_strict → sparse_relaxed → dense_relaxed (last resort)
```

Configure fallbacks in your pipeline YAML:

```yaml
configs:
  science:
    calibrate_image: calibrateImage/tuned_configs/dense_strict.py
    calibrate_image_fallbacks:
      - calibrateImage/tuned_configs/dense_relaxed.py
      - calibrateImage/tuned_configs/sparse_strict.py
      - calibrateImage/tuned_configs/sparse_relaxed.py
```

---

## Nickel Telescope Constraints

These configs are specifically tuned for the Nickel Direct Imaging Camera:

| Property | Value | Impact on Configuration |
|----------|-------|------------------------|
| Detector | 1024x1024 CCD | PSFEx cell sizes must divide evenly into 1024 |
| Pixel scale | 0.37"/pix | Sets relationship between arcsec and pixel tolerances |
| FOV | 6.3' x 6.3' | Small FOV limits number of field stars |
| Typical seeing | 1.5-2.5" (4-7 px) | PSF star width limits, detection thresholds |
| Gain | ~1.8 e-/ADU | Affects S/N calculations |
| Read noise | ~7 e- | Sets practical detection floor |
| Filters | Johnson-Cousins BVRI | B/V bands have fewer bright sources than R/I |
| Pointing accuracy | Variable (100-600 px error) | Drives large `maxOffsetPix` values |
| Rotation | Typically <3 deg | Drives `maxRotationDeg` settings |

---

## Parameter Reference

### PSF Detection (`config.psf_detection`)

Controls which sources are detected as PSF star candidates. This is the first gate — too strict and you lose candidates, too loose and you contaminate the PSF model with noise.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `thresholdValue` | 5.0 | 3.5 | 3.5 | 2.5 | Detection sigma above background. Dense fields can afford high thresholds since they have abundant stars. Sparse fields must go lower to find enough candidates. 2.5-sigma is the practical floor before spurious detections dominate. |
| `includeThresholdMultiplier` | 3.0 | 4.0 | 4.0 | 2.5 | Controls footprint growth beyond the detection threshold. Higher values capture more flux in extended wings. Sparse_relaxed uses 2.5 to keep footprints small and reduce blending. |
| `minPixels` | 7 | 6 | 5 | 5 | Minimum connected pixels for a detection. Strict modes require more pixels to reject cosmic rays and hot pixels. Sparse modes accept smaller objects since seeing may be variable. |
| `doTempWideBackground` | False | False | True | True | Wide-area temporary background subtraction. Useful in sparse fields where few sources make background estimation harder. Not needed in dense fields where local background handles it. |
| `nSigmaToGrow` | 2.0 | 2.0 | 2.5 | 3.0 | Footprint growth sigma. Sparse_relaxed grows aggressively to capture all flux from faint sources. |

**Mask planes** (`excludeMaskPlanes`, `statsMask`):
- **Strict configs** include `SUSPECT` — pixels flagged as questionable are excluded, giving cleaner footprints at the cost of losing some sources.
- **Relaxed configs** omit `SUSPECT` — borderline pixels are allowed through, maximizing the candidate pool.
- **Sparse_relaxed** also omits `CR` from `excludeMaskPlanes` — cosmic ray flags are imperfect and in very sparse fields, losing a source to a false CR flag is worse than including one with a real CR.

### Adaptive Threshold Detection (`config.psf_adaptive_threshold_detection`)

A modern feature in the LSST stack (default enabled) that iteratively adjusts detection thresholds to find isolated, well-separated PSF candidates. Critical for avoiding blended sources in the PSF model.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `minIsolated` | 10 | 6 | 4 | 3 | Minimum isolated sources required. Dense fields demand more to ensure quality. Sparse fields may genuinely have very few isolated sources, so the threshold drops to 3. |
| `sufficientIsolated` | 100 | 50 | 25 | 15 | Target number of isolated sources. Once this many are found, the adaptive loop stops. Reflects realistic expectations for each field density regime. |
| `minFootprint` | 15 | 10 | 8 | 5 | Minimum total footprints (including non-isolated) to proceed. Acts as a sanity check that the detection found enough objects overall. |

### PSF Star Selection (`config.psf_measure_psf.starSelector["objectSize"]`)

After detection, this selector filters candidates by size and signal-to-noise to find actual stars (rejecting galaxies, cosmic rays, and noise).

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `signalToNoiseMin` | 15.0 | 8.0 | 8.0 | 3.0 | S/N floor for PSF star candidates. 15.0 in dense_strict ensures clean, well-measured stars for the best PSF model. 3.0 in sparse_relaxed is the absolute floor — below this, centroid and shape measurements are too noisy to be useful. |
| `widthMin` | 0.8 | 0.6 | 0.6 | 0.4 | Minimum width in sigma units. Rejects cosmic rays and hot pixels which appear point-like (width < seeing). Lower values risk including cosmic rays; higher values risk losing real stars in good seeing. |
| `widthMax` | 8.0 | 10.0 | 10.0 | 12.0 | Maximum width. Rejects extended objects (galaxies, blends). Relaxed modes raise this to accommodate poor seeing where stellar PSFs are genuinely broader. |
| `widthStdAllowed` | 0.35 | 0.45 | 0.5 | 1.0 | Allowed scatter in the width distribution. Stars should cluster tightly in size; a wide scatter indicates contamination by non-stellar objects. Sparse fields inherently have more scatter with fewer samples, hence the relaxation. |
| `nSigmaClip` | 3.0 | 3.5 | 3.5 | 5.0 | Sigma-clipping threshold. Sparse_relaxed uses 5.0 to avoid clipping any of the precious few available stars. |
| `reserve.fraction` | 0.1 | 0.0 | 0.0 | 0.0 | Fraction of PSF stars held out for model validation. Only dense_strict can afford to reserve 10% — all other configs need every star for the PSF model. |

**Bad flags** (`cfg.badFlags`):

The bad flags list controls which pixel-flag conditions disqualify a PSF candidate. The strictness gradient is:

- **dense_strict**: Full list including `nodata`, `interpolatedCenter`, `interpolated` — maximum quality, reject anything questionable.
- **sparse_strict**: Keeps `nodata` and `interpolatedCenter` but drops `interpolated` — a source with any interpolated pixel isn't automatically rejected, only if the center is interpolated.
- **dense_relaxed / sparse_relaxed**: Minimal list — only `edge`, `saturatedCenter`, `crCenter`, `bad`, and `slot_Centroid_flag`. Every marginal source is kept.

### PSF Determiner — PSFEx (`config.psf_measure_psf.psfDeterminer["psfex"]`)

Controls how PSFEx builds the PSF model from selected stars. The key trade-off is spatial complexity vs. data requirements.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `spatialOrder` | 2 | 1 | 1 | 1 | Polynomial order for PSF spatial variation. Order 2 (quadratic) allows the PSF to vary across the 6.3' FOV — important for optical aberrations. Requires ~15+ stars per cell to constrain. Order 1 (linear) is the minimum safe value; order 0 can crash PSFEx. |
| `sizeCellX` / `sizeCellY` | 512 | 512 | 1024 | 1024 | PSF model cell size in pixels. 512 creates a 2x2 grid on the 1024px detector — each cell needs enough stars. 1024 creates a single cell, pooling all stars into one PSF estimate. Essential for sparse fields to avoid "not enough stars per cell" failures. |
| `spatialReject` | 3.0 | 4.0 | 4.0 | 5.0 | Sigma threshold for rejecting outlier candidates from the spatial fit. Strict modes reject at 3-sigma for a cleaner model. Sparse_relaxed uses 5-sigma because rejecting any candidate is costly. |
| `reducedChi2ForPsfCandidates` | 2.0 | 3.0 | 3.0 | 5.0 | Maximum reduced chi-squared for a candidate to be accepted into the PSF model. Strict mode demands candidates fit the model well (chi2 < 2). Sparse_relaxed accepts marginal candidates (chi2 < 5) because the alternative is having too few stars for any model. |
| `samplingSize` | 0.5 | 0.5 | 0.5 | 0.5 | PSF oversampling factor. 0.5 means 2x oversampling, which is standard for Nyquist sampling of the PSF. No reason to vary this across configs. |

### Astrometry — Pattern Matcher (`config.astrometry.matcher`)

The pessimistic pattern matcher (`MatchPessimisticB`) identifies geometric patterns of bright stars and matches them against the reference catalog. This is the most failure-prone step for Nickel data due to poor header WCS.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `maxOffsetPix` | 600 | 1000 | 900 | 1200 | Maximum allowed offset between header WCS and true WCS. Nickel pointing errors can be hundreds of pixels. 600 is tight (for well-pointed fields), 1200 is half the detector width (near-worst-case). |
| `maxRotationDeg` | 2.0 | 3.0 | 3.0 | 5.0 | Maximum allowed rotation. Nickel rotation is typically <3 deg, but sparse_relaxed allows 5 deg as a safety margin. |
| `matcherIterations` | 10 | 12 | 12 | 15 | Number of pattern-matching iterations. More iterations help when there are fewer sources or larger WCS errors. The pattern matcher converges quickly with many stars, but needs more attempts when the search space is larger or candidates are sparse. |
| `minMatchedPairs` | 12 | 8 | 6 | 4 | Minimum matched source pairs for a valid solution. Dense fields can demand 12+ matches. Sparse_relaxed accepts 4 — the theoretical minimum for a robust WCS fit (6 DOF for a TAN-SIP with distortion, but 4 points determine a basic affine). |
| `minFracMatchedPairs` | 0.08 | 0.04 | 0.04 | 0.02 | Minimum fraction of detected sources that must match. Dense fields have many sources, so 8% gives a good absolute count. Sparse_relaxed uses 2% because matching 4/200 is acceptable. |
| `numBrightStars` | 200 | 300 | 200 | 300 | Number of brightest sources to use for pattern matching. Relaxed modes use 300 to cast a wider net when WCS errors make matching harder. |
| `maxRefObjects` | 8000 | 10000 | 6500 | 10000 | Maximum reference catalog objects to load. Dense fields with many refcat sources can limit this for speed. Relaxed modes allow more to increase match probability. |
| `numPatternConsensus` | 3 | 2 | 2 | 2 | Number of independent patterns that must agree. Dense_strict demands 3 for robust consensus. All others accept 2 — the minimum for reasonable confidence. |
| `numPointsForShape` | 6 | 5 | 5 | 4 | Points per asterism in pattern matching. More points make patterns more distinctive but harder to find. Sparse_relaxed uses 4-point asterisms which are easier to match with few stars. |
| `numPointsForShapeAttempt` | 8 | 8 | 7 | 6 | Points attempted before falling back to `numPointsForShape`. Larger asterisms are tried first for reliability, then smaller ones. |

### Astrometry — WCS Fitting (`config.astrometry`)

After pattern matching identifies correspondences, these parameters control the iterative WCS refinement.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `maxIter` | 5 | 7 | 5 | 10 | Maximum WCS fitting iterations. More iterations help converge on poor data but cost time. Sparse_relaxed uses 10 to give the fitter every chance to converge. |
| `maxMeanDistanceArcsec` | 0.5 | 0.8 | 0.6 | 1.5 | Failure threshold: if the mean astrometric residual exceeds this, the solution is rejected. 0.5" is ~1.4 pixels on Nickel — demanding but achievable with good data. 1.5" (~4 pixels) is the last-resort threshold where astrometry is poor but still usable for DIA. |
| `matchDistanceSigma` | 2.0 | 3.0 | 2.5 | 4.0 | Sigma-clipping threshold for match distances during WCS refinement. Wider clipping retains more matches at the cost of noisier fits. |
| `doMagnitudeOutlierRejection` | True | True | True | False | Reject sources whose catalog-vs-measured magnitude discrepancy is an outlier. Helps remove blends and variables. Disabled in sparse_relaxed — too few sources to afford rejecting any. |
| `magnitudeOutlierRejectionNSigma` | 3.0 | 3.5 | 3.0 | — | Sigma threshold for magnitude outlier rejection (when enabled). |
| `sourceSelector.signalToNoise.minimum` | 15.0 | 8.0 | 10.0 | 5.0 | S/N floor for sources used in astrometric fitting. High S/N gives better centroids. Sparse_relaxed uses 5.0 — below this, centroid uncertainty degrades the fit more than having extra sources helps. |

### Astrometry — Reference Catalog (`config.astrometry.referenceSelector`, `config.astrometry_ref_loader`)

Controls which reference catalog stars are loaded and used for matching.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `magLimit.minimum` | 10.0 | 8.0 | 10.0 | 8.0 | Bright magnitude limit. Avoids saturated reference stars. Dense_strict uses 10.0 (safe margin); relaxed modes use 8.0 to include bright stars that may not saturate in short exposures. |
| `magLimit.maximum` | 19.0 | 20.0 | 19.5 | 21.0 | Faint magnitude limit. Sets how deep into the refcat we reach. Sparse_relaxed extends to 21.0 to include faint stars that may be the only available matches. |
| `pixelMargin` | 300 | 500 | 350 | 600 | Pixel margin around the detector for loading refcat sources. Accounts for WCS errors — if the header WCS is off by 500 pixels, we need at least 500 px margin to load the correct refcat region. Dense_strict assumes better WCS; sparse_relaxed prepares for the worst. |

### Photometric Calibration (`config.photometry`)

Controls zero-point determination by matching measured source fluxes to reference catalog magnitudes.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `match.matchRadius` | 3.0 | 5.0 | 4.0 | 6.0 | Matching radius in arcsec (~8-16 pixels on Nickel). Depends on WCS quality — better astrometry allows tighter matching. Strict configs with good WCS can use 3" (~8 px). Sparse_relaxed with potentially 1"+ astrometric residuals needs 6" (~16 px). |
| `sigmaMax` | 0.25 | 0.35 | 0.30 | 0.50 | Maximum sigma for zero-point clipping. Controls how much scatter in the zero-point is tolerated before rejecting sources. 0.25 mag demands excellent agreement; 0.50 mag allows for significant scatter. |
| `nSigma` | 3.0 | 3.0 | 3.0 | 4.0 | Sigma-clipping threshold. Sparse_relaxed uses 4-sigma to retain more photometric matches. |

### Aperture Correction (`config.measure_aperture_correction`)

Measures the correction between PSF flux and aperture flux across the field. Critical for accurate photometry.

| Parameter | dense_strict | dense_relaxed | sparse_strict | sparse_relaxed | Rationale |
|-----------|:---:|:---:|:---:|:---:|-----------|
| `signalToNoise.minimum` | 40.0 | 30.0 | 30.0 | 20.0 | S/N floor for aperture correction sources. Higher S/N gives more precise corrections. Dense_strict demands 40 since plenty of bright stars are available. Sparse_relaxed drops to 20 — the floor below which aperture flux measurements are too noisy. |
| `numSigmaClip` | 3.5 | 4.0 | 4.0 | 5.0 | Sigma-clipping. Relaxed modes use wider clipping to retain more measurements. |
| `numIter` | 5 | 5 | 5 | 4 | Clipping iterations. 5 is standard; sparse_relaxed uses 4 since there are too few sources for iterative clipping to converge meaningfully. |
| `doFinalMedianShift` | True | True | True | True | Ensures the median aperture correction is zero. Prevents systematic photometric biases. Enabled in all configs. |
| `fitConfig.orderX/Y` | (default) | (default) | 0 | 0 | Spatial polynomial order for the aperture correction model. Default allows spatial variation. Sparse fields use zeroth-order (constant) because there are too few stars to constrain spatial variation — fitting a polynomial would just fit noise. |
| `allowFailure` | — | — | — | `["base_GaussianFlux"]` | Allows specific aperture correction plugins to fail without killing the task. Only enabled in sparse_relaxed where GaussianFlux may not have enough sources for a stable correction. |

### PSF Normalized Calibration Flux

A secondary aperture correction for the PSF-normalized calibration flux measurement. Follows the same S/N gradient as the primary aperture correction.

| Config | S/N minimum |
|--------|:-----------:|
| dense_strict | 25.0 |
| sparse_strict | 20.0 |
| dense_relaxed | 18.0 |
| sparse_relaxed | 12.0 |

---

## Choosing a Config

### By Field Characteristics

| Characteristic | Recommended Config |
|----------------|-------------------|
| Low galactic latitude, good seeing | `dense_strict` |
| Low galactic latitude, poor seeing or bad WCS | `dense_relaxed` |
| High galactic latitude, moderate seeing | `sparse_strict` |
| High galactic latitude, poor conditions | `sparse_relaxed` |
| SN host with bright galaxy, few field stars | `sparse_strict` or `sparse_relaxed` |
| Crowded cluster field | `dense_strict` |
| B/V band at high latitude | `sparse_relaxed` (fewer bright blue sources) |

### By Star Count

As a rough guide based on the number of usable PSF candidates in the FOV:

| Stars | Primary Config | Fallback |
|-------|----------------|----------|
| >30 | `dense_strict` | `dense_relaxed` |
| 15-30 | `dense_relaxed` | `sparse_strict` |
| 8-15 | `sparse_strict` | `sparse_relaxed` |
| <8 | `sparse_relaxed` | — |

### Quality Expectations

| Config | Astrometric Residual | Photometric ZP Scatter | Reliability |
|--------|:---:|:---:|:---:|
| dense_strict | <0.3" | <0.05 mag | Moderate — fails on poor data |
| dense_relaxed | <0.5" | <0.10 mag | High |
| sparse_strict | <0.5" | <0.10 mag | Moderate |
| sparse_relaxed | <1.5" | <0.15 mag | Very high — rarely fails |

Results from `sparse_relaxed` should be flagged for manual review due to degraded quality.

---

## Source Code Verification

All parameter names in these configs have been verified against the actual LSST stack source code (scipipe 12.1.0):

| Module | Source File | Config Class |
|--------|------------|--------------|
| `pipe_tasks` | `calibrateImage.py` | `CalibrateImageConfig` |
| `meas_algorithms` | `detection.py` | `SourceDetectionConfig` |
| `meas_algorithms` | `objectSizeStarSelector.py` | `ObjectSizeStarSelectorConfig` |
| `meas_algorithms` | `measureApCorr.py` | `MeasureApCorrConfig` |
| `meas_algorithms` | `adaptive_thresholds.py` | `AdaptiveThresholdDetectionConfig` |
| `meas_extensions_psfex` | `psfexPsfDeterminer.py` | `PsfexPsfDeterminerConfig` |
| `meas_astrom` | `matchPessimisticB.py` | `MatchPessimisticBConfig` |
| `meas_astrom` | `astrometry.py` | `AstrometryConfig` |
| `pipe_tasks` | `photoCal.py` | `PhotoCalConfig` |

Notable findings from the audit:
- `maxBadPixelFraction` does **not** exist in `PsfexPsfDeterminerConfig` — it was present in older configs as a no-op (guarded by `hasattr`). Removed.
- The `psf_determiner` attribute alias does not exist — the correct name is `psfDeterminer`. The `elif` branch in older configs was dead code. Removed.
- Several useful parameters (`spatialReject`, `reducedChi2ForPsfCandidates`, `maxIter`, `maxMeanDistanceArcsec`, `doMagnitudeOutlierRejection`, `sigmaMax`, `doFinalMedianShift`) were not configured in previous versions. Added.

---

## See Also

- [Configuration Guide](configuration.md) - Pipeline YAML and environment setup
- [Architecture Overview](architecture.md) - System architecture
- [CLI Reference](cli-reference.md) - Command-line options
