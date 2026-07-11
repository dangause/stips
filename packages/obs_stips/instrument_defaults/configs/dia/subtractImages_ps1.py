# ruff: noqa: F821
"""
Configuration for subtractImages when using PS1 templates.

FRAMEWORK DEFAULT: this is a REFERENCE tuning from the Nickel 1-m. It is resolved
instrument-dir-first, so a fork can override it by shipping its own
configs/dia/subtractImages_ps1.py (see instrument_defaults/README.md).

PS1 templates have ~1" native seeing, while Nickel science images typically have
1.5-3" seeing. This config optimizes PSF matching for this scenario.

Key settings:
- mode: convolveTemplate — convolve PS1 (better seeing) to match Nickel (worse seeing)
- AL kernel with alard-lupton basis (3 Gaussians, ~27 basis functions)
- Non-spatial kernel (order 0) — avoids underconstrained fits with few stars
- Single cell covering entire image — all kernel stars contribute to one solution
- nStarPerCell = 50 — use many stars for robust kernel fit
- Decorrelation enabled — properly propagates noise through convolution

Why nStarPerCell matters: With nStarPerCell=1 (previous setting), a single bad
kernel candidate (galaxy, blend, edge artifact) produces a negative kernel sum
that inverts the entire subtraction — catastrophic for photometry. With 20-50
candidates typically available on Nickel images, using many stars averages out
individual bad candidates and produces stable positive kernel sums (~100-1000).

Diagnostic evidence (2020wnt PS1, nStarPerCell=1):
  Visit 77524083: ksum=-8356, condnum=1.9e7, 1 star used → bg_std=36231 (BAD)
  Visit 77524086: ksum=+609,  condnum=4.6e6, 1 star used → bg_std=1798  (OK)

IMPORTANT: LSST's config hierarchy for makeKernel:
  config.makeKernel.*              -> MakeKernelConfig fields
  config.makeKernel.kernel.name    -> ChoiceField on MakeKernelConfig (selects active kernel)
  config.makeKernel.kernel["AL"].* -> PsfMatchConfigAL (active when kernel.name="AL")
  config.makeKernel.kernel["DF"].* -> PsfMatchConfigDF (active when kernel.name="DF")
"""

# ==========================================
# PSF Matching Mode
# ==========================================
# convolveTemplate: convolve template to match science PSF.
# Correct when template seeing < science seeing (PS1 ~1" -> Nickel ~2")
config.mode = "convolveTemplate"

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

# ==========================================
# Decorrelation
# ==========================================
# Enable decorrelation to properly propagate noise through the
# convolution — important for accurate source detection and photometry
config.doDecorrelation = True
