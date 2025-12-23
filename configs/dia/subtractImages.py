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
config.makeKernel.spatialOrder = 2

# Kernel size in pixels
# Larger kernel handles PSF mismatches better but slower
# For Nickel: seeing ~1.5-2.5" / 0.37"/pix = 4-7 pixels FWHM
# Kernel should be ~3x FWHM for good sampling
config.makeKernel.kernelSize = 21

# Spatial kernel type
config.makeKernel.kernelSizeType = "square"

# Kernel basis function
config.makeKernel.kernelBasisSet = "alard-lupton"

# Regularization for kernel solution
# Lower = more aggressive fitting, higher = more conservative
config.makeKernel.regularizationType = "tikhonov"
config.makeKernel.lambdaValue = 0.1

# ==========================================
# Background Configuration
# ==========================================

# Subtract backgrounds before differencing
# Critical for accurate photometry
config.doSubtractBackground = True

# Background bin size in pixels
# Smaller = more detailed background model
# For 6 arcmin field, 128 pixels = ~47 arcsec bins
config.makeKernel.makeKernelBasisList.backgroundBinSize = 128

# Use polynomial background subtraction
config.makeKernel.makeKernelBasisList.doBackgroundModelSubtraction = True

# ==========================================
# Source Selection for Kernel
# ==========================================

# Allow automatic detection of kernel sources
# Will find bright, isolated stars for PSF matching
config.allowKernelSourceDetection = True

# Detection configuration for kernel sources
# Want moderately bright, isolated stars (50-sigma)
config.detection.thresholdValue = 50.0
config.detection.thresholdType = "pixel_stdev"
config.detection.minPixels = 5

# Don't include too many faint sources
config.detection.thresholdPolarity = "positive"

# Grow footprints slightly to capture full PSF
config.detection.nSigmaToGrow = 2.5

# ==========================================
# PSF Matching
# ==========================================

# Selecttion criteria for PSF matching stars
# Reject sources near edges, saturated, cosmic rays
config.selectMeasurement.doFlags = True
config.selectMeasurement.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturated",
    "base_PixelFlags_flag_cr",
    "base_PixelFlags_flag_bad",
    "base_PixelFlags_flag_suspect",
]

# S/N cut for kernel stars
# Want high S/N for good PSF estimates
config.selectMeasurement.doSignalToNoise = True
config.selectMeasurement.signalToNoise.minimum = 50.0
config.selectMeasurement.signalToNoise.fluxField = "base_PsfFlux_instFlux"
config.selectMeasurement.signalToNoise.errField = "base_PsfFlux_instFluxErr"

# ==========================================
# Quality Assurance
# ==========================================

# Write QA plots
config.doWriteMatchedExp = True

# Bad pixel handling
config.badMaskPlanes = ["NO_DATA", "BAD", "SAT"]

# Don't mask detections in science image
config.doMaskDetection = False
