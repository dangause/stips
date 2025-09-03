# configs/astrometry_noRoughZP.py
m = config.astrometry.matcher
# keep your post-flip “normal” matcher numbers; e.g.:
m.maxOffsetPix = 120
m.maxRotationDeg = 1.0
m.matcherIterations = 10
m.minMatchedPairs = 12

# <-- This avoids the failure on visits where the refcat has no usable fluxes
config.astrometry.computeRoughZeroPoint = False

# optional: be lenient with ref selection if your refcat lacks mags/flux in some bands
config.astrometry.referenceSelector.magLimit.enabled = False
