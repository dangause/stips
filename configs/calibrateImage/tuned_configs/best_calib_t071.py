# Auto-generated from saved best tuning (trial t071)
# Use top-level assignments only (no functions).

# --- Prelude: keep selector behavior consistent ---
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.doFluxLimit = False
cfg.widthMin = 0.8
cfg.widthMax = 8.0
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

# (Optional but recommended) reference mag limits and star-like refs
# refSel = config.astrometry.referenceSelector
# refSel.doMagLimit = True
# refSel.magLimit.minimum = 12.0
# refSel.magLimit.maximum = 19.0
# refSel.doUnresolved = True
# refSel.doIsolated   = True

# ------------- Tuned values -------------
# PSF detection
config.psf_detection.thresholdValue = 3.1852891079592682
config.psf_detection.includeThresholdMultiplier = 3.8347177138731223

# PSF star selector: objectSize
config.psf_measure_psf.starSelector["objectSize"].signalToNoiseMin = 11.331620382942939
config.psf_measure_psf.starSelector["objectSize"].widthStdAllowed = 0.35714305927818163

# Astrometry matcher (pessimisticB)
m = config.astrometry.matcher
m.maxOffsetPix = int(500)  # INCREASED from 184 for archival data
m.maxRotationDeg = 2.3481849888137583
m.matcherIterations = int(8)
m.minMatchDistPixels = 2.19105964461907
m.minMatchedPairs = int(9)
m.minFracMatchedPairs = 0.06453778850229026
m.numBrightStars = int(200)
m.maxRefObjects = int(6498)
m.numPatternConsensus = int(2)

# Astrometry convergence (RELAXED for better matching)
config.astrometry.maxMeanDistanceArcsec = 100.0  # INCREASED from default 60
config.astrometry.matchDistanceSigma = 10.0  # INCREASED from default 8

# Astrometry science source S/N
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 16.27252713241595

# ApCorr (science selector + clipping)
config.measure_aperture_correction.sourceSelector["science"].signalToNoise.minimum = (
    36.97527026411837
)
config.measure_aperture_correction.numSigmaClip = 3.7130223492394188
config.measure_aperture_correction.numIter = int(5)

# PSF Normalized Calibration Flux (N.C.F.) selector S/N
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector[
    "science"
].signalToNoise.minimum = 22.322792002973504

# ------------- PHOTOMETRIC MATCHING FIXES -------------
# Fix for "No matches to use for photocal" failures
config.photometry.match.matchRadius = 3.5  # INCREASED from default 1.5 arcsec

# --- Nickel PreSource compatibility: add measurement plugins & apertures ---

# Make sure the plugins are enabled
config.star_measurement.plugins.names |= [
    "base_CircularApertureFlux",
    "base_LocalBackground",
    "base_PsfFlux",
    "base_SdssCentroid",  # <- use Sdss centroid (Gaussian variant not present on your stack)
    "base_SdssShape",
    "base_PixelFlags",
    # nice-to-have extras already used in DRP:
    "base_Variance",
    "ext_shapeHSM_HsmPsfMomentsDebiased",
    "ext_shapeHSM_HsmShapeRegauss",
    "base_Blendedness",
    "base_Jacobian",
]

# Aperture configuration (include 17.0 px)
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

# FGCM-friendly compensated tophat apertures
config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]

# (Optional) slot to the 17 px aperture
try:
    config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
except Exception:
    pass
