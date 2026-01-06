# ruff: noqa: F821
"""
Configuration overrides for detectAndMeasureDiaSource task.
"""

# Use stricter residual checks to catch bad subtractions early.
# Fail if residual power in footprints is more than ~5x the science image, and
# if the spatial variation exceeds the same factor.
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0
