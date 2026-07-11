# Sparse-field PSF config using PSFEx with aggressive relaxation
# Adapted from 2023ixf_relaxed_psfex_sparse.py for SN 2020wnt campaign
import os

config_dir = os.path.dirname(__file__)
config.load(os.path.join(config_dir, "2023ixf_relaxed.py"))

# More permissive PSF detection
config.psf_detection.thresholdValue = 2.5
config.psf_detection.includeThresholdMultiplier = 2.5
if hasattr(config.psf_detection, "minPixels"):
    config.psf_detection.minPixels = 5

# Loosen PSF star selector cuts
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 3.0
cfg.doFluxLimit = False
cfg.widthMin = 0.4
cfg.widthMax = 12.0
cfg.widthStdAllowed = 1.0
cfg.nSigmaClip = 5.0
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "slot_Centroid_flag",
]
config.psf_measure_psf.reserve.fraction = 0.0

# Keep PSFEx but reduce spatial complexity / cell starvation
if hasattr(config.psf_measure_psf, "psfDeterminer"):
    config.psf_measure_psf.psfDeterminer.name = "psfex"
    px = config.psf_measure_psf.psfDeterminer["psfex"]
elif hasattr(config.psf_measure_psf, "psf_determiner"):
    config.psf_measure_psf.psf_determiner.name = "psfex"
    px = config.psf_measure_psf.psf_determiner["psfex"]
else:
    px = None

if px is not None:
    if hasattr(px, "spatialOrder"):
        px.spatialOrder = 1
    if hasattr(px, "sizeCellX"):
        px.sizeCellX = 1024
    if hasattr(px, "sizeCellY"):
        px.sizeCellY = 1024
    if hasattr(px, "maxBadPixelFraction"):
        px.maxBadPixelFraction = 0.3

# Astrometry: allow fewer sources
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 5.0
m = config.astrometry.matcher
m.minMatchedPairs = 4
m.minFracMatchedPairs = 0.02
m.numPointsForShape = 4
m.numPointsForShapeAttempt = 6
# ruff: noqa: F821
