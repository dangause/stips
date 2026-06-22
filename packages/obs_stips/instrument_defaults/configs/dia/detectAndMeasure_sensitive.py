# ruff: noqa: F821
"""
Sensitive detection thresholds for low-amplitude variable star DIA sources.

Lowers the detection threshold from 3.0 sigma (supernova default) to 1.5 sigma
to capture subtle variability in difference images. Also reduces minPixels from
5 to 3 to detect smaller footprints from low-amplitude flux changes.

Note: This config is optional and only affects the DIA *source catalog*
(detectAndMeasure). Forced photometry at known RA/Dec coordinates measures flux
at the specified position regardless of detection threshold.

Usage in pipeline YAML:
    configs:
      dia:
        detect_and_measure: dia/detectAndMeasure_sensitive.py
"""

# Bad subtraction rejection (same as standard config)
config.badSubtractionRatioThreshold = 5.0
config.badSubtractionVariationThreshold = 5.0

# Lower detection threshold for subtle variability
if hasattr(config, "detection"):
    config.detection.thresholdValue = 1.5  # sigma (vs 3.0 for SNe)
    config.detection.thresholdType = "stdev"
    config.detection.minPixels = 3  # smaller footprints (vs 5 for SNe)

# Enable sky sources and measurement when supported
if hasattr(config, "doSkySources"):
    config.doSkySources = True
if hasattr(config, "doMeasurement"):
    config.doMeasurement = True
if hasattr(config, "doWriteSubtractedExp"):
    config.doWriteSubtractedExp = True
