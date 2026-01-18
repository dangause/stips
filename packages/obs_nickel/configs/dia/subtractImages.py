"""
Configuration overrides for subtractImages task (Alard-Lupton PSF matching).

This config optimizes image subtraction for Nickel telescope characteristics:
- Typical seeing: 1.5-2.5 arcsec
- Pixel scale: 0.37 arcsec/pixel
- Field of view: ~6 arcmin
"""

# ==========================================
# Kernel Configuration
# ==========================================

# Spatial variation: polynomial order for kernel spatial variation
# Higher order allows kernel to vary more across field
# 2 = good balance for 6 arcmin field
# NOTE: spatialOrder parameter removed in recent LSST stack versions
# config.makeKernel.spatialOrder = 2

# Kernel size in pixels
# Larger kernel handles PSF mismatches better but slower
# For Nickel: seeing ~1.5-2.5" / 0.37"/pix = 4-7 pixels FWHM
# Kernel should be ~3x FWHM for good sampling
config.makeKernel.kernelSize = 21
# Collapse to a single, non-spatial kernel to tolerate sparse stars and small overlap
config.makeKernel.spatialKernelOrder = 0
config.makeKernel.spatialBgOrder = 0
config.makeKernel.iterateSingleKernel = True
# Keep kernel size fixed (do not scale by FWHM) so the small number of stars does not drive
# an oversized basis that becomes ill-conditioned.
config.makeKernel.scaleByFwhm = False
# Prefer the delta-function (DF) kernel basis for robustness with very few kernel stars.
config.makeKernel.kernelBasisSet = "delta-function"
# Use a single huge cell (whole image) and accept at least one star
# Ensure a single cell across the warped template so we don't require per-cell stars
config.makeKernel.sizeCellX = 2048
config.makeKernel.sizeCellY = 2048
config.makeKernel.nStarPerCell = 1
# Match kernel-specific settings to the global single-cell, zero-order model so we do not fall back to the
# default AL/DF grids that expect many stars per cell.
config.makeKernel.kernel["AL"].spatialKernelOrder = 0
config.makeKernel.kernel["AL"].spatialBgOrder = 0
config.makeKernel.kernel["AL"].sizeCellX = 2048
config.makeKernel.kernel["AL"].sizeCellY = 2048
config.makeKernel.kernel["AL"].nStarPerCell = 1
config.makeKernel.kernel["DF"].spatialKernelOrder = 0
config.makeKernel.kernel["DF"].spatialBgOrder = 0
config.makeKernel.kernel["DF"].sizeCellX = 2048
config.makeKernel.kernel["DF"].sizeCellY = 2048
config.makeKernel.kernel["DF"].nStarPerCell = 1
# Loosen kernel-source detection to admit more candidates
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.nSigmaForKernel = 1.5
config.makeKernel.selectDetection.minPixels = 3

# Allow more aggressive PSF matching for large mismatches (PS1 vs Nickel seeing)
config.makeKernel.maxConditionNumber = 1e7  # Increased from default 5e6
config.makeKernel.conditionNumberType = "SVD"

# Note: minKernelSources not available in this LSST stack version
# Sparse field handling is done via nStarPerCell = 1 settings above

# Spatial kernel type
# NOTE: kernelSizeType parameter removed in recent LSST stack versions
# config.makeKernel.kernelSizeType = "square"

# Kernel basis function
# NOTE: kernelBasisSet parameter removed in recent LSST stack versions
# config.makeKernel.kernelBasisSet = "alard-lupton"

# Regularization for kernel solution
# Lower = more aggressive fitting, higher = more conservative
# NOTE: regularizationType and lambdaValue parameters removed in recent LSST stack versions
# config.makeKernel.regularizationType = "tikhonov"
# config.makeKernel.lambdaValue = 0.1

# ==========================================
# Background Configuration
# ==========================================

# Subtract backgrounds before differencing
# Critical for accurate photometry
config.doSubtractBackground = True

# Background bin size in pixels
# Smaller = more detailed background model
# For 6 arcmin field, 128 pixels = ~47 arcsec bins
# NOTE: makeKernelBasisList config structure changed in recent LSST stack versions
# config.makeKernel.makeKernelBasisList.backgroundBinSize = 128

# Use polynomial background subtraction
# NOTE: makeKernelBasisList config structure changed in recent LSST stack versions
# config.makeKernel.makeKernelBasisList.doBackgroundModelSubtraction = True

# ==========================================
# Source Selection for Kernel
# ==========================================

# Allow automatic detection of kernel sources
# Will find bright, isolated stars for PSF matching
config.allowKernelSourceDetection = True

# Detection configuration for kernel sources
# Want moderately bright, isolated stars (50-sigma)
# NOTE: detection config moved/removed from subtractImages in recent LSST stack versions
# config.detection.thresholdValue = 50.0
# config.detection.thresholdType = "pixel_stdev"
# config.detection.minPixels = 5

# Don't include too many faint sources
# NOTE: detection config moved/removed from subtractImages in recent LSST stack versions
# config.detection.thresholdPolarity = "positive"

# Grow footprints slightly to capture full PSF
# NOTE: detection config moved/removed from subtractImages in recent LSST stack versions
# config.detection.nSigmaToGrow = 2.5

# ==========================================
# PSF Matching
# ==========================================

# Selecttion criteria for PSF matching stars
# Reject sources near edges, saturated, cosmic rays
# NOTE: selectMeasurement config moved/removed from subtractImages in recent LSST stack versions
# config.selectMeasurement.doFlags = True
# config.selectMeasurement.flags.bad = [
#     "base_PixelFlags_flag_edge",
#     "base_PixelFlags_flag_saturated",
#     "base_PixelFlags_flag_cr",
#     "base_PixelFlags_flag_bad",
#     "base_PixelFlags_flag_suspect",
# ]

# S/N cut for kernel stars
# Want high S/N for good PSF estimates
# NOTE: selectMeasurement config moved/removed from subtractImages in recent LSST stack versions
# config.selectMeasurement.doSignalToNoise = True
# config.selectMeasurement.signalToNoise.minimum = 50.0
# config.selectMeasurement.signalToNoise.fluxField = "base_PsfFlux_instFlux"
# config.selectMeasurement.signalToNoise.errField = "base_PsfFlux_instFluxErr"

# ==========================================
# Quality Assurance
# ==========================================

# Write QA plots
# NOTE: doWriteMatchedExp parameter removed in recent LSST stack versions
# config.doWriteMatchedExp = True

# Bad pixel handling
# NOTE: badMaskPlanes config may have moved in recent LSST stack versions
# config.badMaskPlanes = ["NO_DATA", "BAD", "SAT"]

# Don't mask detections in science image
# NOTE: doMaskDetection parameter may have moved in recent LSST stack versions
# config.doMaskDetection = False
# ruff: noqa: F821
