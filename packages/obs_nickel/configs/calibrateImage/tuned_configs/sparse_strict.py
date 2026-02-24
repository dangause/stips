# Sparse-field STRICT science processing config for Nickel 1m telescope
#
# Use case: Fields with few usable stars (~8-25 PSF candidates).
#   - High galactic latitude targets
#   - Short exposures where only bright stars are detected
#   - Fields dominated by one bright galaxy (SN host) with few field stars
#   - Moderate-to-good seeing nights
#
# Philosophy: Adapt PSF modeling and matching to work with few stars while
# maintaining quality standards where possible. Key trade-offs vs dense:
#   - Lower detection threshold to find more candidates
#   - Simplified PSF spatial model (order 1, large cells)
#   - Fewer required matches, but still demand reasonable S/N
#   - PSFEx with single large cell to avoid cell starvation
#
# This config is optimized for the "just enough stars" regime: you have
# some good stars, but not many. It will fail if <6 stars are usable —
# use sparse_relaxed.py as fallback.
#
# Nickel constraints:
#   - 1024x1024 CCD, 0.37"/pix, 6.3' FOV
#   - At high galactic latitude: typically 10-30 stars in FOV to mag ~20
#   - Typical seeing 1.5-2.5" (4-7 px FWHM)
#
# Intended fallback chain:
#   sparse_strict → sparse_relaxed → (dense_relaxed as last resort)
#
# ruff: noqa: F821

import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "best_calib_t071.py"))

# =============================================================================
# PSF DETECTION — cast a wider net for candidates
# =============================================================================
# Lower threshold to find fainter stars. In sparse fields, we need every
# candidate we can get, but still reject obvious noise/artifacts.
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = 3.5  # lower than dense strict (5.0)
config.psf_detection.includeThresholdMultiplier = 4.0  # wider footprints
config.psf_detection.minPixels = 5  # allow slightly smaller objects
config.psf_detection.reEstimateBackground = True
config.psf_detection.doTempLocalBackground = True
config.psf_detection.doTempWideBackground = True  # helps with sparse bg estimation
config.psf_detection.isotropicGrow = True
config.psf_detection.nSigmaToGrow = 2.5
config.psf_detection.combinedGrow = True

# Mask planes: omit SUSPECT to keep borderline sources in sparse fields
config.psf_detection.excludeMaskPlanes = ["EDGE", "SAT", "CR", "BAD", "NO_DATA"]
config.psf_detection.statsMask = ["BAD", "SAT", "EDGE", "NO_DATA"]

# =============================================================================
# ADAPTIVE THRESHOLD DETECTION
# =============================================================================
# Lower isolation requirements for sparse fields — fewer candidates available.
config.do_adaptive_threshold_detection = True
config.psf_adaptive_threshold_detection.minIsolated = 4
config.psf_adaptive_threshold_detection.sufficientIsolated = 25
config.psf_adaptive_threshold_detection.minFootprint = 8

# =============================================================================
# PSF STAR SELECTION — accept more candidates, still with quality checks
# =============================================================================
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 8.0  # lower than dense strict (15.0) but still reasonable
cfg.doFluxLimit = False
cfg.widthMin = 0.6  # allow slightly tighter objects
cfg.widthMax = 10.0  # seeing variation may be larger with few samples
cfg.widthStdAllowed = 0.5  # allow wider scatter (fewer samples = noisier stats)
cfg.nSigmaClip = 3.5

# Moderate bad-pixel flagging: keep most defaults but omit SUSPECT
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_nodata",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "slot_Centroid_flag",
    # SUSPECT and interpolated omitted: in sparse fields, borderline sources may be needed
]

# No reserve — cannot afford to lose any PSF stars
config.psf_measure_psf.reserve.fraction = 0.0

# =============================================================================
# PSF DETERMINER (PSFEx) — simplified spatial model for few stars
# =============================================================================
# PSFEx with spatialOrder=1 and a single large cell spanning the whole
# detector. This avoids the "not enough stars per cell" failure that
# kills processing in sparse fields with the default grid.
px = config.psf_measure_psf.psfDeterminer["psfex"]
px.spatialOrder = 1  # linear variation only (needs fewer stars)
px.sizeCellX = 1024  # single cell: all stars contribute to one model
px.sizeCellY = 1024
px.spatialReject = 4.0  # moderate rejection — can't lose too many stars
px.reducedChi2ForPsfCandidates = 3.0  # more permissive than dense strict (2.0)
px.samplingSize = 0.5  # standard 2x oversampling

# =============================================================================
# ASTROMETRY
# =============================================================================
# Sparse fields mean fewer detected sources for pattern matching. Allow
# generous initial tolerances but demand reasonable final solution quality.
m = config.astrometry.matcher
m.maxOffsetPix = 900  # generous for Nickel pointing errors
m.maxRotationDeg = 3.0
m.matcherIterations = 12  # more iterations to compensate for fewer sources
m.minMatchDistPixels = 2.0
m.minMatchedPairs = 6  # lower than dense (12) — may only have 10-20 stars
m.minFracMatchedPairs = 0.04  # lower fraction: few sources means low absolute count
m.numBrightStars = 200
m.maxRefObjects = 6500
m.numPatternConsensus = 2  # accept fewer agreeing patterns
m.numPointsForShape = 5
m.numPointsForShapeAttempt = 7  # slightly fewer than dense

# AstrometryTask WCS fitting parameters
config.astrometry.maxIter = 5  # enough iterations for convergence
config.astrometry.maxMeanDistanceArcsec = (
    0.6  # slightly more tolerant than dense strict (0.5)
)
config.astrometry.matchDistanceSigma = 2.5  # moderate match distance clipping
config.astrometry.doMagnitudeOutlierRejection = True
config.astrometry.magnitudeOutlierRejectionNSigma = 3.0

# Moderate S/N cut — can't be too aggressive with few sources
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 10.0

# Standard refcat selection
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = 10.0
config.astrometry.referenceSelector.magLimit.maximum = 19.5

config.astrometry_ref_loader.pixelMargin = 350

# =============================================================================
# PHOTOMETRIC CALIBRATION
# =============================================================================
config.photometry.match.matchRadius = 4.0  # arcsec — moderate tolerance
config.photometry.sigmaMax = 0.30  # moderate: between dense strict and relaxed
config.photometry.nSigma = 3.0  # sigma-clipping for photometry

# =============================================================================
# APERTURE CORRECTION
# =============================================================================
# Moderate thresholds: need enough sources for stable aperture correction
# but can't demand as much S/N as dense fields.
c = config.measure_aperture_correction
c.sourceSelector["science"].signalToNoise.minimum = 30.0
c.numSigmaClip = 4.0
c.numIter = 5
c.doFinalMedianShift = True  # ensure median of corrections is zero

# Flatten the aperture correction model: with few stars, spatial variation
# is unconstrained. Use zeroth-order (constant) model.
c.fitConfig.orderX = 0
c.fitConfig.orderY = 0

config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 20.0
