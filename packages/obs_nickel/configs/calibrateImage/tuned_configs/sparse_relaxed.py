# Sparse-field RELAXED science processing config for Nickel 1m telescope
#
# Use case: Last-resort config for the most challenging frames.
#   - Very few stars (<10 usable PSF candidates)
#   - High galactic latitude with poor seeing (FWHM > 2.5")
#   - Short exposures or non-photometric conditions
#   - Frames that failed all other configs
#
# Philosophy: Do whatever it takes to get a WCS solution and PSF model,
# even if quality is degraded. Accept astrometry scatter of ~1" and
# photometry scatter of ~0.1 mag if that's the best achievable. This is
# specifically designed for the "we have 4-8 stars and they're faint"
# scenario that is common on Nickel at high galactic latitude.
#
# Key extreme relaxations vs other configs:
#   - Detection threshold down to 2.5 sigma
#   - PSF star S/N minimum at 3.0 (absolute floor)
#   - Only 4 matched pairs required for astrometry
#   - Single-cell constant PSF model (no spatial variation)
#   - Very wide matching tolerances (1200 px offset, 5 deg rotation)
#   - Zeroth-order aperture correction
#
# WARNING: Results from this config should be flagged for manual review.
# Photometric and astrometric quality will be significantly degraded
# compared to strict/relaxed configs.
#
# Nickel constraints:
#   - 1024x1024 CCD, 0.37"/pix, 6.3' FOV
#   - At high latitude: may have only 5-15 detectable stars
#   - B/V bands particularly challenging (fewer bright sources)
#
# Intended use: End of fallback chain for sparse fields, or as standalone
# config when you know the field is extremely sparse.
#
# ruff: noqa: F821

import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "best_calib_t071.py"))

# =============================================================================
# PSF DETECTION — catch everything plausible
# =============================================================================
# Aggressive low threshold. Risk of including spurious sources is
# acceptable — the PSF star selector will filter downstream.
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = 2.5  # very low: find every star
config.psf_detection.includeThresholdMultiplier = 2.5  # moderate growth
config.psf_detection.minPixels = 5  # small sources OK
config.psf_detection.reEstimateBackground = True
config.psf_detection.doTempLocalBackground = True
config.psf_detection.doTempWideBackground = True  # essential for sparse bg estimation
config.psf_detection.isotropicGrow = True
config.psf_detection.nSigmaToGrow = 3.0  # grow footprints more aggressively
config.psf_detection.combinedGrow = True

# Minimal mask planes: only the essentials to maximize detections
config.psf_detection.excludeMaskPlanes = ["EDGE", "SAT", "BAD", "NO_DATA"]
config.psf_detection.statsMask = ["BAD", "SAT", "EDGE", "NO_DATA"]

# =============================================================================
# ADAPTIVE THRESHOLD DETECTION
# =============================================================================
# Very low requirements — sparse fields may barely meet these thresholds.
config.do_adaptive_threshold_detection = True
config.psf_adaptive_threshold_detection.minIsolated = 3
config.psf_adaptive_threshold_detection.sufficientIsolated = 15
config.psf_adaptive_threshold_detection.minFootprint = 5

# =============================================================================
# PSF STAR SELECTION — accept nearly anything that looks stellar
# =============================================================================
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 3.0  # absolute floor: accept faint stars
cfg.doFluxLimit = False
cfg.widthMin = 0.4  # allow very tight sources (possible undersampled PSF)
cfg.widthMax = 12.0  # very generous — bad seeing can broaden significantly
cfg.widthStdAllowed = 1.0  # very wide: with few stars, scatter is high
cfg.nSigmaClip = 5.0  # very lenient: don't clip precious few stars

# Minimal bad-pixel flagging: only reject the most egregious problems
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "slot_Centroid_flag",
]

# Absolutely no reserve — every star is needed
config.psf_measure_psf.reserve.fraction = 0.0

# =============================================================================
# PSF DETERMINER (PSFEx) — constant PSF model across detector
# =============================================================================
# Force PSFEx with spatialOrder=1 (minimum safe) and a single huge cell.
# With <10 stars, any spatial variation is noise, not signal. A single-cell
# model uses ALL stars for one PSF estimate, maximizing stability.
px = config.psf_measure_psf.psfDeterminer["psfex"]
px.spatialOrder = 1  # minimum (0 can crash PSFEx)
px.sizeCellX = 1024  # entire detector = one cell
px.sizeCellY = 1024
px.spatialReject = 5.0  # very lenient: can't afford to lose stars
px.reducedChi2ForPsfCandidates = 5.0  # very permissive: accept marginal candidates
px.samplingSize = 0.5  # standard 2x oversampling

# =============================================================================
# ASTROMETRY — maximum tolerance
# =============================================================================
# The widest possible gate. Nickel pointing can be hundreds of pixels off,
# and with very few sources the pattern matcher needs all the help it can get.
m = config.astrometry.matcher
m.maxOffsetPix = 1200  # maximum: half the detector width
m.maxRotationDeg = 5.0  # very generous rotation tolerance
m.matcherIterations = 15  # many iterations: let it search hard
m.minMatchDistPixels = 3.0  # loose final tolerance
m.minMatchedPairs = 4  # absolute minimum: 4 stars
m.minFracMatchedPairs = 0.02  # very low fraction
m.numBrightStars = 300  # try matching with more refcat stars
m.maxRefObjects = 10000
m.numPatternConsensus = 2
m.numPointsForShape = 4  # smaller asterisms (easier to find with few stars)
m.numPointsForShapeAttempt = 6

# AstrometryTask WCS fitting parameters — maximum tolerance
config.astrometry.maxIter = 10  # many iterations for very poor data
config.astrometry.maxMeanDistanceArcsec = 1.5  # accept ~1.5" mean residual
config.astrometry.matchDistanceSigma = 4.0  # very wide match distance clipping
config.astrometry.doMagnitudeOutlierRejection = (
    False  # disable: too few sources to reject
)

# Very low S/N cut: use every detected source for matching
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 5.0

# Wide refcat magnitude range: include faint stars that might be our only match
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = 8.0
config.astrometry.referenceSelector.magLimit.maximum = 21.0

# Maximum pixel margin: tolerate the worst initial WCS
config.astrometry_ref_loader.pixelMargin = 600

# =============================================================================
# PHOTOMETRIC CALIBRATION
# =============================================================================
# Wide matching radius: WCS may be poor (~1" residuals)
config.photometry.match.matchRadius = 6.0  # arcsec — ~16 pixels
config.photometry.sigmaMax = 0.5  # very permissive ZP clipping
config.photometry.nSigma = 4.0  # lenient sigma-clipping

# =============================================================================
# APERTURE CORRECTION
# =============================================================================
# Minimal requirements: if we have even a few PSF stars, try to
# compute an aperture correction.
c = config.measure_aperture_correction
c.sourceSelector["science"].signalToNoise.minimum = 20.0  # lower than other configs
c.numSigmaClip = 5.0  # very lenient clipping
c.numIter = 4
c.doFinalMedianShift = True  # ensure median of corrections is zero

# Zeroth-order (constant) model: no spatial variation with few stars
c.fitConfig.orderX = 0
c.fitConfig.orderY = 0

# Allow GaussianFlux aperture correction to fail without killing the whole task
c.allowFailure = ["base_GaussianFlux"]

# Very relaxed normalized calibration flux
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 12.0
