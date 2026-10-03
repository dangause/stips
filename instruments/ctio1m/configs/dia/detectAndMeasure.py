# ruff: noqa: F821
"""CTIO Y4KCam DIA detection/measurement overrides.

Mirrors the framework default, plus the key Y4KCam change: exclude the SAT/INTRP
mask planes from difference detection. ISR masks bright-star bleed wings
(growSaturationFootprintSize, see the profile), but the stack default
``detection.excludeMaskPlanes = []`` means detection still fires on those masked
pixels -> the bleeds are detected as trailed sources (~40-57% of all detections
on the dense SA98 standard field). Excluding SAT/INTRP (and the saturated-
template plane) skips them. Science and template share the same bright stars, so
the science SAT mask covers the difference residual at those positions.
"""

# Catch bad subtractions early (framework default).
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0

if hasattr(config, "detection"):
    config.detection.thresholdValue = 5.0
    config.detection.thresholdType = "stdev"
    config.detection.minPixels = 5
    # The fix: don't detect on saturated / interpolated (bleed) pixels.
    config.detection.excludeMaskPlanes = [
        "SAT",
        "INTRP",
        "BAD",
        "EDGE",
        "NO_DATA",
    ]

if hasattr(config, "doSkySources"):
    config.doSkySources = True
if hasattr(config, "doMeasurement"):
    config.doMeasurement = True
if hasattr(config, "doWriteSubtractedExp"):
    config.doWriteSubtractedExp = True
