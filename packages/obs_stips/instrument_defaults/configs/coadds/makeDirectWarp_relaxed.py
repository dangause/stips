# ruff: noqa: F821

# Very relaxed warp selection for coadd templates.
#
# FRAMEWORK DEFAULT: REFERENCE tuning from the Nickel 1-m, resolved
# instrument-dir-first (a fork can override with its own
# configs/coadds/makeDirectWarp_relaxed.py; see instrument_defaults/README.md).
#
# The Nickel 1-m telescope produces images with larger PSF variations
# than LSST defaults allow. These thresholds are very relaxed to accept
# visits that would otherwise be rejected, accepting that template quality
# may be somewhat degraded.
#
# WARNING: Very relaxed thresholds may allow visits with poor PSF models
# or marginal WCS solutions. Use with caution.
#
# Default thresholds (from LSST stack) vs Nickel values:
#   maxPsfApFluxDelta:       0.24 → 2.0  (PSF aperture flux variation)
#   maxPsfTraceRadiusDelta:  0.70 → 3.0  (PSF trace radius variation)
#   maxEllipResidual:        0.015 → 0.05 (PSF ellipticity residual)
#   maxScaledSizeScatter:    0.022 → 0.25 (PSF size scatter) - was 0.03

# Warp selection subtask thresholds - very relaxed for template building
config.select.maxPsfApFluxDelta = 2.0
config.select.maxPsfTraceRadiusDelta = 3.0
config.select.maxEllipResidual = 0.05
config.select.maxScaledSizeScatter = 0.25
