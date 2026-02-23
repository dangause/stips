# ruff: noqa: F821
"""
Configuration for subtractImages when using PS1 templates.

PS1 templates have ~1" native seeing, while Nickel science images typically have
1.5-3" seeing. This config optimizes PSF matching for this scenario.

Key settings:
- mode: convolveTemplate — convolve PS1 (better seeing) to match Nickel (worse seeing)
- AL kernel with delta-function basis — numerically stable for sparse fields
- Non-spatial kernel (order 0) — avoids underconstrained fits with few stars
- Single cell covering entire image — all 3-12 kernel stars contribute to one solution

IMPORTANT: LSST's config hierarchy for makeKernel is:
  config.makeKernel.*              -> MakeKernelConfig (NOT used at runtime for PsfMatch fields)
  config.makeKernel.kernel["AL"].* -> PsfMatchConfigAL (USED at runtime when kernel.name="AL")

PsfMatchTask.__init__ sets self.kConfig = self.config.kernel.active, so ALL PsfMatchConfig-
inherited fields MUST be set on kernel["AL"] or kernel["DF"] to take effect.
"""

# ==========================================
# PSF Matching Mode
# ==========================================
# convolveTemplate: convolve template to match science PSF.
# Correct when template seeing < science seeing (PS1 ~1" -> Nickel ~2")
config.mode = "convolveTemplate"

# ==========================================
# Kernel Configuration (on active kernel config)
# ==========================================
# Use AL framework with delta-function basis — same proven approach as subtractImages.py.
# Delta-function basis with non-spatial fitting needs only ~21 parameters (kernel pixels)
# and works with as few as 1-2 kernel stars.

config.makeKernel.kernel["AL"].kernelBasisSet = "delta-function"
config.makeKernel.kernel["AL"].kernelSize = 21
config.makeKernel.kernel["AL"].scaleByFwhm = False
config.makeKernel.kernel["AL"].spatialKernelOrder = 0
config.makeKernel.kernel["AL"].spatialBgOrder = 0
config.makeKernel.kernel["AL"].sizeCellX = 2048
config.makeKernel.kernel["AL"].sizeCellY = 2048
config.makeKernel.kernel["AL"].nStarPerCell = 1
config.makeKernel.kernel["AL"].iterateSingleKernel = True
config.makeKernel.kernel["AL"].fitForBackground = True
config.makeKernel.kernel["AL"].maxConditionNumber = 1e7
config.makeKernel.kernel["AL"].conditionNumberType = "SVD"

# Also configure DF sub-config consistently
config.makeKernel.kernel["DF"].kernelSize = 21
config.makeKernel.kernel["DF"].scaleByFwhm = False
config.makeKernel.kernel["DF"].spatialKernelOrder = 0
config.makeKernel.kernel["DF"].spatialBgOrder = 0
config.makeKernel.kernel["DF"].sizeCellX = 2048
config.makeKernel.kernel["DF"].sizeCellY = 2048
config.makeKernel.kernel["DF"].nStarPerCell = 1
config.makeKernel.kernel["DF"].iterateSingleKernel = True
config.makeKernel.kernel["DF"].fitForBackground = True

# ==========================================
# Kernel Source Detection (MakeKernelConfig-level — correct)
# ==========================================
config.allowKernelSourceDetection = True
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.minPixels = 3

# ==========================================
# Background Configuration
# ==========================================
config.doSubtractBackground = True
