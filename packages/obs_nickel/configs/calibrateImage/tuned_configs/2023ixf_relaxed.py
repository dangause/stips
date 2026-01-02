# Relaxed astrometry config for 2023ixf with poor initial WCS
# Based on best_calib_t071.py but with more permissive matching

# Import all settings from best_calib_t071
import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "best_calib_t071.py"))

# Override astrometry settings to be MORE relaxed
m = config.astrometry.matcher
m.maxOffsetPix = 1200  # Allow even larger initial WCS errors
m.maxRotationDeg = 3.0  # Allow more rotation
m.matcherIterations = 12  # More iterations to find solution
m.minMatchedPairs = 6  # Lower minimum (was 9)
m.minFracMatchedPairs = 0.03  # Lower fraction (was 0.06)
m.numBrightStars = 300  # Use more bright stars
m.maxRefObjects = 10000  # Allow more reference objects

# Relax source S/N cuts for astrometry matching
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 8.0  # was 16.27

# Widen refcat magnitude range
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = 10.0  # was 8.0
config.astrometry.referenceSelector.magLimit.maximum = 20.0  # was 18.0

# Increase pixel margin for refcat loading
config.astrometry_ref_loader.pixelMargin = 500  # was 250

# Allow larger photometry matching radius for poor WCS
config.photometry.match.matchRadius = 6.0  # was 4.0 arcsec
# ruff: noqa: F821
