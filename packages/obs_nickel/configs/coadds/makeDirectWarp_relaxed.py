# ruff: noqa: F821

# Tightened warp selection for Nickel coadd templates.
#
# The Nickel 1-m telescope produces images with larger PSF variations
# than LSST defaults allow. These thresholds are relaxed relative to
# LSST defaults but tightened from earlier values (2.0/3.0/0.05/0.05)
# to reject visits with marginal PSF models that often correlate with
# poor WCS solutions — which cause severely distorted warps in the coadd.
#
# Default thresholds (from LSST stack) vs Nickel values:
#   maxPsfApFluxDelta:       0.24 → 1.0  (PSF aperture flux variation)
#   maxPsfTraceRadiusDelta:  0.70 → 1.5  (PSF trace radius variation)
#   maxEllipResidual:        0.015 → 0.03 (PSF ellipticity residual)
#   maxScaledSizeScatter:    0.022 → 0.03 (PSF size scatter)

# Warp selection subtask thresholds
config.select.maxPsfApFluxDelta = 1.0
config.select.maxPsfTraceRadiusDelta = 1.5
config.select.maxEllipResidual = 0.03
config.select.maxScaledSizeScatter = 0.03
