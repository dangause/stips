# Loosen PSF-pass detection so we actually get some peaks
config.psf_detection.thresholdValue = 3.0              # from 5.0
config.psf_detection.includeThresholdMultiplier = 6.0  # ~18σ include
config.psf_detection.doTempWideBackground = True
