# ruff: noqa: F821
"""
Configuration for subtractImages when using PS1 templates.

PS1 templates have ~1" native seeing, while Nickel science images typically have
1.5-3" seeing. This config optimizes PSF matching for this scenario.

Key settings:
- mode: convolveTemplate - Convolve PS1 (better seeing) to match Nickel (worse seeing)
- delta-function kernel basis - Numerically stable for sparse fields
- Non-spatial kernel (order 0) - Avoids underconstrained fits with few stars

IMPORTANT: Nickel fields typically have only 3-12 usable kernel stars.
The Alard-Lupton basis with spatial variation requires 31+ parameters,
which is catastrophically underconstrained. Use delta-function basis instead.
"""

# ==========================================
# PSF Matching Mode
# ==========================================
# convolveTemplate: Convolve template to match science PSF
# This is correct when template seeing < science seeing (PS1 ~1" → Nickel ~2")
config.mode = "convolveTemplate"

# ==========================================
# Kernel Configuration (Numerically Stable)
# ==========================================

# Fixed kernel size - don't scale by FWHM to avoid ill-conditioned basis
config.makeKernel.kernelSize = 21
config.makeKernel.scaleByFwhm = False

# SELECT the delta-function kernel (not just configure it!)
# AL basis with 3 Gaussians + polynomial variation = 31 parameters
# DF basis with constant kernel = ~21 parameters (kernel size)
# CRITICAL: kernel.name selects which kernel type to use
config.makeKernel.kernel.name = "DF"

# Non-spatial kernel (constant across image)
# Critical for sparse fields - spatial variation needs many stars per cell
config.makeKernel.spatialKernelOrder = 0
config.makeKernel.spatialBgOrder = 0

# Single large cell covering entire image
# Accept just 1 star if that's all we have
config.makeKernel.sizeCellX = 2048
config.makeKernel.sizeCellY = 2048
config.makeKernel.nStarPerCell = 1

# Iterate to refine kernel
config.makeKernel.iterateSingleKernel = True

# Fit for background difference
config.makeKernel.fitForBackground = True

# Allow detection of kernel sources
config.allowKernelSourceDetection = True

# Lenient source selection for sparse fields
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.minPixels = 3

# Condition number limits - tighter to reject ill-conditioned solutions
config.makeKernel.checkConditionNumber = True
config.makeKernel.maxConditionNumber = 1e5  # Tighter limit (was 1e7)

# Kernel sum clipping - reject candidates with anomalous flux scaling
config.makeKernel.kernelSumClipping = True
config.makeKernel.maxKsumSigma = 3.0  # Reject 3-sigma outliers

# ==========================================
# Kernel Basis Settings (both AL and DF)
# ==========================================
# Match the non-spatial, single-cell settings for both basis types
# so fallback behavior is consistent

config.makeKernel.kernel["AL"].spatialKernelOrder = 0
config.makeKernel.kernel["AL"].spatialBgOrder = 0
config.makeKernel.kernel["AL"].sizeCellX = 2048
config.makeKernel.kernel["AL"].sizeCellY = 2048
config.makeKernel.kernel["AL"].nStarPerCell = 1

# DF kernel specific settings
config.makeKernel.kernel["DF"].spatialKernelOrder = 0
config.makeKernel.kernel["DF"].spatialBgOrder = 0
config.makeKernel.kernel["DF"].sizeCellX = 2048
config.makeKernel.kernel["DF"].sizeCellY = 2048
config.makeKernel.kernel["DF"].nStarPerCell = 1
config.makeKernel.kernel["DF"].iterateSingleKernel = True
config.makeKernel.kernel["DF"].fitForBackground = True
config.makeKernel.kernel["DF"].scaleByFwhm = False
config.makeKernel.kernel["DF"].kernelSize = 21

# ==========================================
# Background Configuration
# ==========================================
config.doSubtractBackground = True

# ==========================================
# Decorrelation
# ==========================================
# Enable decorrelation to properly propagate noise
config.doDecorrelation = True
