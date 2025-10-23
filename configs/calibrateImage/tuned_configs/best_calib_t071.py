# # Auto-generated from saved best tuning (trial t071)
# # BALANCED: Adjusted for science images while maintaining quality
# # Use top-level assignments only (no functions).

# # --- Prelude: keep selector behavior consistent ---
# cfg = config.psf_measure_psf.starSelector["objectSize"]
# cfg.doSignalToNoiseLimit = True
# cfg.doFluxLimit = False
# cfg.widthMin = 0.8
# cfg.widthMax = 8.0
# cfg.nSigmaClip = 3.0
# config.psf_measure_psf.reserve.fraction = 0.0

# ss = config.astrometry.sourceSelector["science"]
# ss.doSignalToNoise = True

# c = config.measure_aperture_correction
# c.sourceSelector.name = "science"
# css = c.sourceSelector["science"]
# css.doSignalToNoise = True
# css.signalToNoise.maximum = None

# ncf = config.psf_normalized_calibration_flux.measure_ap_corr
# ncf.sourceSelector.name = "science"
# nss = ncf.sourceSelector["science"]
# nss.doSignalToNoise = True
# nss.doUnresolved = False
# nss.doIsolated = False

# # ------------- BALANCED Detection Thresholds -------------
# # The original was giving 12σ effective threshold (3.19 × 3.83)
# # Lower to 5σ which is standard for astronomy
# config.psf_detection.thresholdValue = 5.0  # Standard 5σ detection
# config.psf_detection.includeThresholdMultiplier = 1.0  # No multiplier

# # ------------- BALANCED PSF Star Selection Criteria -------------
# # Original S/N of 11.3 was too high - lower to 8.0 for good star quality
# config.psf_measure_psf.starSelector["objectSize"].signalToNoiseMin = 8.0

# # Keep original width constraints - they were reasonable
# # widthMin = 0.8, widthMax = 8.0 already set above
# # widthStdAllowed stays at default

# # ------------- Astrometry Parameters (slightly relaxed from original) -------------
# m = config.astrometry.matcher
# m.maxOffsetPix = int(500)  # Keep increased from 184 for archival data
# m.maxRotationDeg = 2.3481849888137583  # Keep original
# m.matcherIterations = int(8)  # Keep original
# m.minMatchDistPixels = 2.19105964461907  # Keep original
# m.minMatchedPairs = int(9)  # Keep original
# m.minFracMatchedPairs = 0.06453778850229026  # Keep original
# m.numBrightStars = int(200)  # Keep original
# m.maxRefObjects = int(6498)  # Keep original
# m.numPatternConsensus = int(2)  # Keep original

# # Astrometry convergence (keep relaxed for archival data)
# config.astrometry.maxMeanDistanceArcsec = 100.0  # Keep increased
# config.astrometry.matchDistanceSigma = 10.0  # Keep increased

# # Astrometry science source S/N - slightly lower than original
# config.astrometry.sourceSelector["science"].signalToNoise.minimum = 12.0  # Lowered from 16.3

# # ------------- ApCorr Parameters (slightly relaxed) -------------
# config.measure_aperture_correction.sourceSelector[
#     "science"
# ].signalToNoise.minimum = 25.0  # Lowered from 37.0
# config.measure_aperture_correction.numSigmaClip = 3.7130223492394188  # Keep original
# config.measure_aperture_correction.numIter = int(5)  # Keep original

# # PSF Normalized Calibration Flux selector S/N - slightly lower
# config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
#     "science"
# ].signalToNoise.minimum = 18.0  # Lowered from 22.3

# # ------------- PHOTOMETRIC MATCHING FIXES -------------
# config.photometry.match.matchRadius = 3.5  # Keep increased

# # --- Nickel PreSource compatibility: add measurement plugins & apertures ---
# config.star_measurement.plugins.names |= [
#     "base_CircularApertureFlux",
#     "base_LocalBackground",
#     "base_PsfFlux",
#     "base_SdssCentroid",
#     "base_SdssShape",
#     "base_PixelFlags",
#     "base_Variance",
#     "ext_shapeHSM_HsmPsfMomentsDebiased",
#     "ext_shapeHSM_HsmShapeRegauss",
#     "base_Blendedness",
#     "base_Jacobian",
# ]

# config.star_measurement.plugins["base_CircularApertureFlux"].radii = [
#     3.0,
#     6.0,
#     9.0,
#     12.0,
#     17.0,
#     25.0,
#     35.0,
#     50.0,
#     70.0,
# ]
# config.star_measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0

# config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
# config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]

# try:
#     config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
# except Exception:
#     pass


# Auto-generated from saved best tuning (trial t071)
# SPARSE FIELD MODE: For supernova/galaxy fields with very few available stars
# Use top-level assignments only (no functions).

# --- Prelude: keep selector behavior consistent ---
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.doFluxLimit = False
cfg.widthMin = 0.5  # Very permissive
cfg.widthMax = 10.0  # Very permissive
cfg.nSigmaClip = 3.0
config.psf_measure_psf.reserve.fraction = 0.0

ss = config.astrometry.sourceSelector["science"]
ss.doSignalToNoise = True

c = config.measure_aperture_correction
c.sourceSelector.name = "science"
css = c.sourceSelector["science"]
css.doSignalToNoise = True
css.signalToNoise.maximum = None

ncf = config.psf_normalized_calibration_flux.measure_ap_corr
ncf.sourceSelector.name = "science"
nss = ncf.sourceSelector["science"]
nss.doSignalToNoise = True
nss.doUnresolved = False
nss.doIsolated = False

# ------------- VERY PERMISSIVE Detection Thresholds -------------
config.psf_detection.thresholdValue = 4.0  # Lower to 4σ
config.psf_detection.includeThresholdMultiplier = 1.0

# ------------- VERY PERMISSIVE PSF Star Selection -------------
# Critical: Lower S/N to accept fainter stars
config.psf_measure_psf.starSelector["objectSize"].signalToNoiseMin = (
    5.0  # Very low threshold
)

# Lower spatial order to minimum for sparse fields
config.psf_measure_psf.psfDeterminer["psfex"].spatialOrder = 0  # No spatial variation

# ------------- Astrometry Parameters (relaxed) -------------
m = config.astrometry.matcher
m.maxOffsetPix = int(500)
m.maxRotationDeg = 2.3481849888137583
m.matcherIterations = int(8)
m.minMatchDistPixels = 2.19105964461907
m.minMatchedPairs = int(6)  # Lowered to accept fewer matches
m.minFracMatchedPairs = 0.05  # Lowered
m.numBrightStars = int(200)
m.maxRefObjects = int(6498)
m.numPatternConsensus = int(2)

# Astrometry convergence (relaxed)
config.astrometry.maxMeanDistanceArcsec = 100.0
config.astrometry.matchDistanceSigma = 10.0

# Astrometry science source S/N - very low for faint fields
config.astrometry.sourceSelector["science"].signalToNoise.minimum = (
    8.0  # Lowered significantly
)

# ------------- ApCorr Parameters (very relaxed) -------------
config.measure_aperture_correction.sourceSelector["science"].signalToNoise.minimum = (
    15.0  # Very low
)
config.measure_aperture_correction.numSigmaClip = 3.7130223492394188
config.measure_aperture_correction.numIter = int(5)

# PSF Normalized Calibration Flux selector S/N - very low
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 12.0  # Very low

# ------------- PHOTOMETRIC MATCHING FIXES -------------
config.photometry.match.matchRadius = 3.5

# --- Nickel PreSource compatibility: add measurement plugins & apertures ---
config.star_measurement.plugins.names |= [
    "base_CircularApertureFlux",
    "base_LocalBackground",
    "base_PsfFlux",
    "base_SdssCentroid",
    "base_SdssShape",
    "base_PixelFlags",
    "base_Variance",
    "ext_shapeHSM_HsmPsfMomentsDebiased",
    "ext_shapeHSM_HsmShapeRegauss",
    "base_Blendedness",
    "base_Jacobian",
]

config.star_measurement.plugins["base_CircularApertureFlux"].radii = [
    3.0,
    6.0,
    9.0,
    12.0,
    17.0,
    25.0,
    35.0,
    50.0,
    70.0,
]
config.star_measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0

config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]

try:
    config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
except Exception:
    pass
