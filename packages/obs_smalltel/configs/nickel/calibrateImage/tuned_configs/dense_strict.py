# Dense-field STRICT science processing config for Nickel 1m telescope
#
# Use case: Fields with abundant bright stars (>30 usable PSF candidates).
#   - Low/moderate galactic latitude targets
#   - Fields with resolved galaxy backgrounds (M101, etc.)
#   - Good seeing nights (FWHM < 2.0")
#
# Philosophy: Maximize astrometric and photometric quality. Demand high S/N
# for all calibration steps. Reject marginal sources aggressively. This
# produces the best possible calibration when enough stars are available,
# but will fail on star-poor frames — use dense_relaxed.py as fallback.
#
# Nickel constraints informing these choices:
#   - 1024x1024 CCD, 0.37"/pix, 6.3' FOV
#   - Typical seeing 1.5-2.5" (4-7 px FWHM)
#   - Gain ~1.8 e-/ADU, read noise ~7 e-
#   - Single amplifier, single detector
#   - Johnson-Cousins BVRI filter set
#
# Intended fallback chain:
#   dense_strict → dense_relaxed → sparse_relaxed
#
# ruff: noqa: F821

import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "best_calib_t071.py"))

# =============================================================================
# PSF DETECTION — find PSF star candidates
# =============================================================================
# High threshold ensures only well-measured stars enter PSF modeling.
# Dense fields have plenty of candidates, so we can afford to be picky.
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = 5.0  # ~5-sigma: clean, well-detected sources only
config.psf_detection.includeThresholdMultiplier = 3.0  # footprint growth: moderate
config.psf_detection.minPixels = 7  # require at least 7 connected pixels
config.psf_detection.reEstimateBackground = True
config.psf_detection.doTempLocalBackground = True
config.psf_detection.doTempWideBackground = False  # not needed in dense fields
config.psf_detection.isotropicGrow = True
config.psf_detection.nSigmaToGrow = 2.0
config.psf_detection.combinedGrow = True

# Exclude SUSPECT pixels from detection to keep footprints clean
config.psf_detection.excludeMaskPlanes = [
    "EDGE",
    "SAT",
    "CR",
    "BAD",
    "NO_DATA",
    "SUSPECT",
]
config.psf_detection.statsMask = ["BAD", "SAT", "EDGE", "NO_DATA", "SUSPECT"]

# =============================================================================
# ADAPTIVE THRESHOLD DETECTION
# =============================================================================
# Use the adaptive detection scheme (default True in modern stack).
# Demand more isolated sources for PSF modeling in dense fields where
# blending is the main concern.
config.do_adaptive_threshold_detection = True
config.psf_adaptive_threshold_detection.minIsolated = 10
config.psf_adaptive_threshold_detection.sufficientIsolated = 100
config.psf_adaptive_threshold_detection.minFootprint = 15

# =============================================================================
# PSF STAR SELECTION — choose stars for PSF model
# =============================================================================
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 15.0  # demand high S/N PSF stars for clean model
cfg.doFluxLimit = False
cfg.widthMin = 0.8  # exclude cosmic rays / hot pixels (in sigma units)
cfg.widthMax = 8.0  # exclude galaxies and blended objects
cfg.widthStdAllowed = 0.35  # tight: stars should cluster well in size
cfg.nSigmaClip = 3.0  # standard sigma-clipping

# Strict bad-pixel flagging: reject anything questionable
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_nodata",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "base_PixelFlags_flag_interpolated",
    "slot_Centroid_flag",
]

# Reserve some stars for PSF model validation when we can afford it
config.psf_measure_psf.reserve.fraction = 0.1

# =============================================================================
# PSF DETERMINER (PSFEx) — build the PSF model
# =============================================================================
# In dense fields, allow moderate spatial variation since we have enough
# stars to constrain it. Use tighter rejection thresholds for quality.
px = config.psf_measure_psf.psfDeterminer["psfex"]
px.spatialOrder = 2  # allow PSF variation across 6.3' field
px.sizeCellX = 512  # 2 cells across the 1024px detector
px.sizeCellY = 512
px.spatialReject = 3.0  # reject candidates >3-sigma from spatial fit
px.reducedChi2ForPsfCandidates = 2.0  # chi2 threshold for candidate acceptance
px.samplingSize = 0.5  # standard 2x oversampling

# =============================================================================
# ASTROMETRY — WCS fitting
# =============================================================================
# Tight matcher settings. Nickel header WCS can be off by hundreds of pixels,
# but in strict mode we still allow moderate offset while demanding more
# pattern consensus and matched pairs.
m = config.astrometry.matcher
m.maxOffsetPix = 600  # moderate: allow for Nickel pointing errors
m.maxRotationDeg = 2.0  # typical Nickel rotation uncertainty
m.matcherIterations = 10  # enough iterations to converge
m.minMatchDistPixels = 2.0  # final match tolerance in pixels
m.minMatchedPairs = 12  # demand more matches than relaxed modes
m.minFracMatchedPairs = 0.08  # require 8% of sources to match
m.numBrightStars = 200  # use 200 brightest for pattern matching
m.maxRefObjects = 8000  # dense fields have many refcat sources
m.numPatternConsensus = 3  # require 3 agreeing patterns (robust)
m.numPointsForShape = 6  # 6-point asterisms for pattern recognition
m.numPointsForShapeAttempt = 8  # try 8-point asterisms first

# AstrometryTask WCS fitting parameters
config.astrometry.maxIter = 5  # more iterations for convergence
config.astrometry.maxMeanDistanceArcsec = 0.5  # fail if mean residual > 0.5"
config.astrometry.matchDistanceSigma = 2.0  # match distance clipping sigma
config.astrometry.doMagnitudeOutlierRejection = True
config.astrometry.magnitudeOutlierRejectionNSigma = 3.0

# Source S/N cut for astrometry: use only well-measured sources
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 15.0

# Reference catalog selection: tight magnitude range for clean stars
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = 10.0  # avoid saturated
config.astrometry.referenceSelector.magLimit.maximum = 19.0  # avoid faint/noisy

# Refcat loading margin — smaller for dense fields (less WCS error expected
# on fields where pattern matching works well)
config.astrometry_ref_loader.pixelMargin = 300

# =============================================================================
# PHOTOMETRIC CALIBRATION
# =============================================================================
# Tight matching radius: good WCS means photometry matches should be close
config.photometry.match.matchRadius = 3.0  # arcsec — ~8 pixels
config.photometry.sigmaMax = 0.25  # max sigma for ZP clipping
config.photometry.nSigma = 3.0  # sigma-clipping for photometry

# =============================================================================
# APERTURE CORRECTION
# =============================================================================
# Demand high S/N sources for aperture correction (critical for photometry)
c = config.measure_aperture_correction
c.sourceSelector["science"].signalToNoise.minimum = 40.0  # high bar
c.numSigmaClip = 3.5
c.numIter = 5
c.doFinalMedianShift = True  # ensure median of corrections is zero

# PSF normalized calibration flux: also high S/N requirement
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 25.0
