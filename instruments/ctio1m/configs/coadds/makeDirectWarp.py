# ruff: noqa: F821
# CTIO Y4KCam direct-warp selection. Mirrors the framework relaxed warp config
# (coadds/makeDirectWarp_relaxed.py) — Y4KCam has fewer, larger-PSF-variation
# visits than LSST defaults expect. Retune at validation if warps are rejected.
config.select.maxPsfApFluxDelta = 2.0
config.select.maxPsfTraceRadiusDelta = 3.0
config.select.maxEllipResidual = 0.05
config.select.maxScaledSizeScatter = 0.25
