# ruff: noqa: F821
"""
Configuration overrides for subtractImages task (Nickel-to-Nickel DIA).

Optimized for Nickel telescope characteristics:
- Typical seeing: 1.5-2.5 arcsec
- Pixel scale: 0.37 arcsec/pixel
- Field of view: ~6 arcmin (2048x2048 pixels)
- Typically 20-50 kernel candidate stars per visit

Uses the AL (Alard-Lupton) kernel with default 3-Gaussian basis set.
The alard-lupton basis has ~27 basis functions, which is well-constrained
with multiple kernel stars averaging out individual bad candidates.

nStarPerCell = 50: Critical for robust kernel fitting. With nStarPerCell=1
(previous setting), a single bad candidate produces a negative kernel sum that
inverts the entire subtraction. With 20-50 candidates available per visit,
using many stars produces stable kernel sums and clean difference images.

IMPORTANT: LSST's config hierarchy for makeKernel:
  config.makeKernel.*              -> MakeKernelConfig fields
  config.makeKernel.kernel.name    -> ChoiceField on MakeKernelConfig (selects active kernel)
  config.makeKernel.kernel["AL"].* -> PsfMatchConfigAL (active when kernel.name="AL")
  config.makeKernel.kernel["DF"].* -> PsfMatchConfigDF (active when kernel.name="DF")

PsfMatchTask.__init__ reads self.config.kernel.active, so PsfMatchConfig-inherited fields
(spatialKernelOrder, sizeCellX, kernelSize, etc.) MUST be set on kernel["AL"] or kernel["DF"].
"""

# ==========================================
# Kernel: AL with alard-lupton basis (default)
# ==========================================
# kernel.name defaults to "AL" — no override needed.
# kernelBasisSet defaults to "alard-lupton" (3 Gaussians) — no override needed.

# Nickel-specific overrides for sparse fields:
config.makeKernel.kernel["AL"].kernelSize = 21
config.makeKernel.kernel["AL"].scaleByFwhm = False
config.makeKernel.kernel["AL"].spatialKernelOrder = 0  # Non-spatial: too few stars
config.makeKernel.kernel["AL"].spatialBgOrder = 0  # Non-spatial background
config.makeKernel.kernel["AL"].sizeCellX = 2048  # Single cell = entire image
config.makeKernel.kernel["AL"].sizeCellY = 2048
config.makeKernel.kernel["AL"].nStarPerCell = 50  # Use many stars for robust kernel

# ==========================================
# Kernel Source Detection
# ==========================================
config.allowKernelSourceDetection = True
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.nSigmaForKernel = 1.5
config.makeKernel.selectDetection.minPixels = 3

# ==========================================
# Condition Number / Kernel Sum Quality
# ==========================================
# Reject kernel candidates with poor condition numbers
config.makeKernel.checkConditionNumber = True
config.makeKernel.maxConditionNumber = 1e5

# Reject kernel candidates with anomalous flux scaling
config.makeKernel.kernelSumClipping = True
config.makeKernel.maxKsumSigma = 3.0

# ==========================================
# Background Configuration
# ==========================================
config.doSubtractBackground = True
