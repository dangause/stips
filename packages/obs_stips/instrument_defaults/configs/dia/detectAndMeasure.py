# ruff: noqa: F821
"""
Configuration overrides for detectAndMeasureDiaSource task.
"""

# Use stricter residual checks to catch bad subtractions early.
# Fail if residual power in footprints is more than ~5x the science image, and
# if the spatial variation exceeds the same factor.
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0

# Detection thresholds for transient searches.
if hasattr(config, "detection"):
    config.detection.thresholdValue = 3.0
    config.detection.thresholdType = "stdev"
    config.detection.minPixels = 5

# Enable sky sources and measurement when supported by the stack version.
if hasattr(config, "doSkySources"):
    config.doSkySources = True
if hasattr(config, "doMeasurement"):
    config.doMeasurement = True
if hasattr(config, "doWriteSubtractedExp"):
    config.doWriteSubtractedExp = True
