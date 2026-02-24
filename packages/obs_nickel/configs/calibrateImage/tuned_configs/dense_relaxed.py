# Dense-field RELAXED science processing config for Nickel 1m telescope
#
# Use case: Fallback for dense fields when strict config fails.
#   - Fields with many stars but poor initial WCS, bad seeing, or
#     marginal observing conditions
#   - Galaxy-contaminated fields where star/galaxy separation is harder
#   - Frames where astrometry failed under strict settings
#
# Philosophy: Keep enough sources for reliable calibration, but loosen
# all the gates that might reject a frame entirely. Accept slightly
# noisier astrometry/photometry in exchange for completing processing.
# This is the "first fallback" for dense fields.
#
# Key differences from dense_strict:
#   - Lower S/N thresholds for PSF stars and astrometry sources
#   - Wider matching tolerances (offset, rotation, match radius)
#   - Fewer required matched pairs
#   - Looser PSF star width selection
#   - More generous refcat magnitude range
#   - Larger pixel margin for refcat loading
#
# Nickel constraints:
#   - 1024x1024 CCD, 0.37"/pix, 6.3' FOV
#   - Typical seeing 1.5-2.5" (4-7 px FWHM)
#   - Gain ~1.8 e-/ADU, read noise ~7 e-
#
# Intended fallback chain:
#   dense_strict → dense_relaxed → (sparse_strict → sparse_relaxed)
#
# ruff: noqa: F821

import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "best_calib_t071.py"))

# =============================================================================
# PSF DETECTION — find PSF star candidates
# =============================================================================
# Lower threshold to catch more candidates, helping in poor conditions.
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = 3.5  # lower than strict (5.0)
config.psf_detection.includeThresholdMultiplier = 4.0  # grow footprints more
config.psf_detection.minPixels = 6
config.psf_detection.reEstimateBackground = True
config.psf_detection.doTempLocalBackground = True
config.psf_detection.doTempWideBackground = False
config.psf_detection.isotropicGrow = True
config.psf_detection.nSigmaToGrow = 2.0
config.psf_detection.combinedGrow = True

# Mask planes: omit SUSPECT to allow borderline pixels through
config.psf_detection.excludeMaskPlanes = ["EDGE", "SAT", "CR", "BAD", "NO_DATA"]
config.psf_detection.statsMask = ["BAD", "SAT", "EDGE", "NO_DATA"]

# =============================================================================
# ADAPTIVE THRESHOLD DETECTION
# =============================================================================
# Enable adaptive detection. Lower isolation requirements than strict since
# poor conditions may reduce the number of cleanly isolated sources.
config.do_adaptive_threshold_detection = True
config.psf_adaptive_threshold_detection.minIsolated = 6
config.psf_adaptive_threshold_detection.sufficientIsolated = 50
config.psf_adaptive_threshold_detection.minFootprint = 10

# =============================================================================
# PSF STAR SELECTION
# =============================================================================
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 8.0  # lower bar than strict (15.0)
cfg.doFluxLimit = False
cfg.widthMin = 0.6  # slightly more permissive than strict (0.8)
cfg.widthMax = 10.0  # allow broader PSFs from poor seeing
cfg.widthStdAllowed = 0.45  # wider cluster tolerance than strict (0.35)
cfg.nSigmaClip = 3.5  # slightly more lenient clipping

# Relaxed bad-pixel flagging: omit SUSPECT, interpolated, nodata to keep more candidates
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "slot_Centroid_flag",
]

# Don't reserve stars — need every candidate for PSF model
config.psf_measure_psf.reserve.fraction = 0.0

# =============================================================================
# PSF DETERMINER (PSFEx)
# =============================================================================
# Still allow spatial variation, but reduce order to avoid over-fitting
# when conditions are poor.
px = config.psf_measure_psf.psfDeterminer["psfex"]
px.spatialOrder = 1  # reduce from 2 to avoid over-fitting
px.sizeCellX = 512  # same as strict — still enough stars in dense fields
px.sizeCellY = 512
px.spatialReject = 4.0  # looser rejection than strict (3.0)
px.reducedChi2ForPsfCandidates = 3.0  # more permissive than strict (2.0)
px.samplingSize = 0.5  # standard 2x oversampling

# =============================================================================
# ASTROMETRY
# =============================================================================
# Wider tolerances for Nickel header WCS errors and poor conditions.
m = config.astrometry.matcher
m.maxOffsetPix = 1000  # generous: Nickel WCS can be way off
m.maxRotationDeg = 3.0  # allow larger rotation mismatch
m.matcherIterations = 12  # more iterations to converge on poor data
m.minMatchDistPixels = 2.5  # slightly looser final tolerance
m.minMatchedPairs = 8  # fewer than strict (12)
m.minFracMatchedPairs = 0.04  # half of strict (0.08)
m.numBrightStars = 300  # use more bright stars for matching
m.maxRefObjects = 10000  # allow more refcat objects
m.numPatternConsensus = 2  # accept with fewer agreeing patterns
m.numPointsForShape = 5  # relaxed from 6
m.numPointsForShapeAttempt = 8

# AstrometryTask WCS fitting parameters — more tolerant than strict
config.astrometry.maxIter = 7  # more iterations for poor data
config.astrometry.maxMeanDistanceArcsec = (
    0.8  # allow larger mean residual than strict (0.5)
)
config.astrometry.matchDistanceSigma = 3.0  # wider match distance clipping
config.astrometry.doMagnitudeOutlierRejection = True
config.astrometry.magnitudeOutlierRejectionNSigma = 3.5

# Lower source S/N for astrometry to use more sources
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 8.0

# Wider refcat magnitude range
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = 8.0
config.astrometry.referenceSelector.magLimit.maximum = 20.0

# Larger pixel margin for refcat loading (tolerate worse initial WCS)
config.astrometry_ref_loader.pixelMargin = 500

# =============================================================================
# PHOTOMETRIC CALIBRATION
# =============================================================================
# Wider matching radius: WCS may not be as tight as strict mode
config.photometry.match.matchRadius = 5.0  # arcsec — ~14 pixels
config.photometry.sigmaMax = 0.35  # more permissive than strict (0.25)
config.photometry.nSigma = 3.0  # sigma-clipping for photometry

# =============================================================================
# APERTURE CORRECTION
# =============================================================================
# More lenient S/N thresholds since we may have fewer high-S/N stars
c = config.measure_aperture_correction
c.sourceSelector["science"].signalToNoise.minimum = 30.0
c.numSigmaClip = 4.0
c.numIter = 5
c.doFinalMedianShift = True  # ensure median of corrections is zero

# Relaxed normalized calibration flux
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 18.0
