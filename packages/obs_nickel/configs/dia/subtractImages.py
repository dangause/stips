# ruff: noqa: F821
"""
Configuration overrides for subtractImages task (Alard-Lupton PSF matching).

Optimized for Nickel telescope characteristics:
- Typical seeing: 1.5-2.5 arcsec
- Pixel scale: 0.37 arcsec/pixel
- Field of view: ~6 arcmin (2048x2048 pixels)
- Sparse fields: typically 3-12 usable kernel stars

IMPORTANT: LSST's config hierarchy for makeKernel is:
  config.makeKernel.*              -> MakeKernelConfig (NOT used at runtime for PsfMatch fields)
  config.makeKernel.kernel["AL"].* -> PsfMatchConfigAL (USED at runtime when kernel.name="AL")
  config.makeKernel.kernel["DF"].* -> PsfMatchConfigDF (USED at runtime when kernel.name="DF")

PsfMatchTask.__init__ sets self.kConfig = self.config.kernel.active, so ALL PsfMatchConfig-
inherited fields (spatialKernelOrder, sizeCellX, kernelBasisSet, etc.) MUST be set on the
kernel["AL"] or kernel["DF"] sub-config to take effect.  Settings on config.makeKernel.* for
these fields are silently ignored at runtime.
"""

# ==========================================
# Kernel Selection: AL with delta-function basis
# ==========================================
# Use the Alard-Lupton framework but with delta-function basis functions.
# This is the most stable approach for Nickel's sparse fields:
# - AL framework handles kernel fitting, clipping, background
# - Delta-function basis is numerically stable with few stars
# - Non-spatial (constant) kernel avoids underconstrained spatial fits
#
# kernelBasisSet controls which basis functions makeKernelBasisList() creates:
#   "alard-lupton"   -> sum-of-Gaussians (27 params with 3 Gaussians)
#   "delta-function" -> one delta-function per kernel pixel (~21 params for 21x21)
#
# kernel.name selects the config CLASS (AL or DF), which provides defaults and
# additional parameters. We keep kernel.name="AL" (default) and override the
# basis set to delta-function within it.

# -- Active kernel config (THESE SETTINGS TAKE EFFECT) --
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

# Also configure DF sub-config consistently (in case kernel.name is switched)
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
# Kernel Source Detection (on MakeKernelConfig - these DO take effect)
# ==========================================
# selectDetection is specific to MakeKernelConfig, not PsfMatchConfig,
# so setting it on config.makeKernel.* is correct.
config.allowKernelSourceDetection = True
config.makeKernel.selectDetection.thresholdValue = 1.5
config.makeKernel.selectDetection.nSigmaForKernel = 1.5
config.makeKernel.selectDetection.minPixels = 3

# ==========================================
# Background Configuration
# ==========================================
config.doSubtractBackground = True
