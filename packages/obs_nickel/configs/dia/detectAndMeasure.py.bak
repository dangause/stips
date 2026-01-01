"""
Configuration overrides for detectAndMeasureDiaSource task.

This config optimizes DIA source detection and measurement for Nickel:
- Lower detection threshold for faint transients
- Robust measurement algorithms
- False positive filtering via sky sources
"""

# ==========================================
# Detection Configuration
# ==========================================

# Detection threshold: 3-sigma for transients
# Lower than normal source detection to catch faint variables
config.detection.thresholdValue = 3.0
config.detection.thresholdType = "stdev"

# Minimum connected pixels
# Small sources OK for point-source transients
config.detection.minPixels = 5

# Detect both positive and negative sources
# Negative = possible template artifacts or photometric variability
config.detection.thresholdPolarity = "both"

# Background estimation for detection
config.detection.reEstimateBackground = True
config.detection.background.approxOrderX = 1
config.detection.background.approxOrderY = 1

# Footprint growing
# Moderate grow to capture full PSF but not merge nearby sources
config.detection.nSigmaToGrow = 2.0

# Temporary local background for faint sources
config.detection.doTempLocalBackground = True
config.detection.tempLocalBackground.binSize = 64

# ==========================================
# Measurement Configuration
# ==========================================

# Enable measurement on difference image
config.doMeasurement = True

# Measurement plugins to run
config.measurement.plugins.names = [
    # Core measurements
    "base_SkyCoord",  # RA/Dec coordinates
    "base_PsfFlux",  # PSF photometry (primary for point sources)
    "base_CircularApertureFlux",  # Aperture photometry (multiple radii)
    "base_GaussianFlux",  # Gaussian fit flux
    # Shape measurements
    "base_SdssShape",  # Adaptive moments shape
    "ext_shapeHSM_HsmSourceMoments",  # HSM shape measurements
    # Flags and classification
    "base_PixelFlags",  # Pixel-level flags (bad, saturated, etc.)
    "base_ClassificationExtendedness",  # Star/galaxy separator
    # Centroids
    "base_NaiveCentroid",  # Simple centroid
    "base_SdssCentroid",  # SDSS centroid algorithm
]

# ==========================================
# PSF Flux (Primary Measurement)
# ==========================================

# PSF flux is primary measurement for point sources
config.measurement.slots.psfFlux = "base_PsfFlux"
config.measurement.plugins["base_PsfFlux"].doMeasure = True

# ==========================================
# Aperture Flux Configuration
# ==========================================

# Primary aperture flux
config.measurement.slots.apFlux = "base_CircularApertureFlux_12_0"

# Aperture radii in pixels
# For Nickel: typical PSF FWHM = 4-7 pixels (1.5-2.5 arcsec / 0.37"/pix)
# Use apertures: 1x, 2x, 3x, 4x FWHM
# 12 pixels ≈ 2x median FWHM, good balance
config.measurement.plugins["base_CircularApertureFlux"].radii = [
    3.0,
    6.0,
    9.0,
    12.0,
    18.0,
    24.0,
]
config.measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0

# ==========================================
# Shape Measurements
# ==========================================

# SDSS adaptive moments
config.measurement.slots.shape = "base_SdssShape"
config.measurement.plugins["base_SdssShape"].doMeasure = True

# HSM shape measurements (more robust for faint sources)
config.measurement.plugins["ext_shapeHSM_HsmSourceMoments"].doMeasure = True

# ==========================================
# Centroid Configuration
# ==========================================

config.measurement.slots.centroid = "base_SdssCentroid"
config.measurement.plugins["base_SdssCentroid"].doMeasure = True
config.measurement.plugins["base_SdssCentroid"].binmax = 16

# ==========================================
# Sky Sources (False Positive Estimation)
# ==========================================

# Enable sky source injection for false positive rate estimation
config.doSkySources = True

# Number of sky sources to inject
# ~10% of typical source count
config.skySources.nSources = 100

# Avoid placing sky sources on real detections or bad pixels
config.skySources.avoidMask = [
    "DETECTED",
    "DETECTED_NEGATIVE",
    "BAD",
    "SAT",
    "NO_DATA",
    "SUSPECT",
]

# ==========================================
# Dipole Fitting
# ==========================================

# Enable dipole measurement for moving objects/artifacts
config.doMerge = True
config.measurement.plugins["base_PsfFlux"].doMeasure = True

# ==========================================
# Output Configuration
# ==========================================

# Write difference exposure with detections marked
config.doWriteSubtractedExp = True

# Write kernel sources catalog
config.doWriteKernelSources = False

# ==========================================
# Quality Flags
# ==========================================

# Bad pixel flags to propagate
config.badMaskPlanes = ["NO_DATA", "BAD", "SAT", "SUSPECT"]

# Flag sources near edges
config.measurement.plugins["base_PixelFlags"].doMeasure = True
config.measurement.plugins["base_PixelFlags"].masksFpAnywhere = [
    "NO_DATA",
    "BAD",
    "SAT",
]
config.measurement.plugins["base_PixelFlags"].masksFpCenter = [
    "SUSPECT",
    "CLIPPED",
]
