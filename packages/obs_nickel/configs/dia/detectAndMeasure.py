# ruff: noqa: F821
"""
Configuration overrides for detectAndMeasureDiaSource task.
"""

# Relying on task defaults - minimal config for compatibility
# Allow bad subtraction residuals (temporary to evaluate PS1 template)
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0
