# ruff: noqa: F821

# Relaxed warp selection for Nickel B/V-band coadd templates.
#
# The Nickel 1-m telescope produces B/V-band images with larger PSF
# variations than the default thresholds allow. These relaxed settings
# permit more visits to contribute to the coadd template at the cost
# of slightly lower template quality.
#
# Default thresholds (from LSST stack) vs relaxed values:
#   maxPsfApFluxDelta:       0.24 → 2.0  (PSF aperture flux variation)
#   maxPsfTraceRadiusDelta:  0.70 → 3.0  (PSF trace radius variation)
#   maxEllipResidual:        0.015 → 0.05 (PSF ellipticity residual)
#   maxScaledSizeScatter:    0.022 → 0.05 (PSF size scatter)

# Warp selection subtask thresholds
config.select.maxPsfApFluxDelta = 2.0
config.select.maxPsfTraceRadiusDelta = 3.0
config.select.maxEllipResidual = 0.05
config.select.maxScaledSizeScatter = 0.05
