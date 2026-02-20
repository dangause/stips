# ruff: noqa: F821
"""
Configuration for subtractImages when using PS1 templates.

PS1 templates have ~1" native seeing, while Nickel science images typically have
1.5-3" seeing. This config optimizes PSF matching for this scenario.

Key settings:
- mode: convolveTemplate - Convolve PS1 (better seeing) to match Nickel (worse seeing)
- kernelSize: 25 - Larger kernel for bigger PSF mismatch
- Use Alard-Lupton basis for flexible kernel shapes
"""

# ==========================================
# PSF Matching Mode
# ==========================================
# convolveTemplate: Convolve template to match science PSF
# This is correct when template seeing < science seeing (PS1 ~1" → Nickel ~2")
config.mode = "convolveTemplate"

# ==========================================
# Kernel Configuration
# ==========================================

# Larger kernel size for significant PSF mismatch
# PS1→Nickel requires convolving ~1" to ~2-3"
config.makeKernel.kernelSize = 25
config.makeKernel.kernelSizeMin = 21
config.makeKernel.kernelSizeMax = 35

# Use Alard-Lupton basis for more flexible PSF matching
config.makeKernel.kernelBasisSet = "alard-lupton"

# Allow spatially varying kernel if enough stars
config.makeKernel.spatialKernelOrder = 1
config.makeKernel.spatialBgOrder = 1

# Scale kernel size by FWHM difference
config.makeKernel.scaleByFwhm = True

# Kernel fitting parameters
config.makeKernel.iterateSingleKernel = True
config.makeKernel.singleKernelClipping = True
config.makeKernel.spatialKernelClipping = True

# Fit for background difference
config.makeKernel.fitForBackground = True

# Allow detection of kernel sources
config.allowKernelSourceDetection = True

# More lenient source selection for sparse fields
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.minPixels = 3

# Relaxed star selection for Nickel sparse fields
config.makeKernel.sizeCellX = 512
config.makeKernel.sizeCellY = 512
config.makeKernel.nStarPerCell = 2
config.minKernelSources = 2

# Condition number limits
config.makeKernel.checkConditionNumber = True
config.makeKernel.maxConditionNumber = 1e7

# ==========================================
# Alard-Lupton Kernel Parameters
# ==========================================
# Configure AL basis for PS1→Nickel PSF matching
# Typical sigma range: 0.7-3.0 pixels for 1"→2.5" mismatch

config.makeKernel.kernel["AL"].alardNGauss = 3
config.makeKernel.kernel["AL"].alardSigGauss = [0.7, 1.5, 3.0]
config.makeKernel.kernel["AL"].alardDegGauss = [4, 3, 2]
config.makeKernel.kernel["AL"].fitForBackground = True

# Spatial variation
config.makeKernel.kernel["AL"].spatialKernelOrder = 1
config.makeKernel.kernel["AL"].spatialBgOrder = 1
config.makeKernel.kernel["AL"].sizeCellX = 512
config.makeKernel.kernel["AL"].sizeCellY = 512
config.makeKernel.kernel["AL"].nStarPerCell = 2

# ==========================================
# Background Configuration
# ==========================================
config.doSubtractBackground = True

# ==========================================
# Decorrelation
# ==========================================
# Enable decorrelation to properly propagate noise
config.doDecorrelation = True
