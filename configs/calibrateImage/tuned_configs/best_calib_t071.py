# Auto-generated from saved best tuning (trial t071)
# IMPORTANT: this file is executed by pipetask with `config` in scope.
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
# Uncomment if you want the stricter reference selection you tried earlier.
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
config.psf_measure_psf.starSelector["objectSize"].widthStdAllowed  = 0.35714305927818163

# Astrometry matcher (pessimisticB)
m = config.astrometry.matcher
m.maxOffsetPix         = int(184)
m.maxRotationDeg       = 2.3481849888137583
m.matcherIterations    = int(8)
m.minMatchDistPixels   = 2.19105964461907
m.minMatchedPairs      = int(9)
m.minFracMatchedPairs  = 0.06453778850229026
m.numBrightStars       = int(200)
m.maxRefObjects        = int(6498)
m.numPatternConsensus  = int(2)

# Astrometry science source S/N
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 16.27252713241595

# ApCorr (science selector + clipping)
config.measure_aperture_correction.sourceSelector["science"].signalToNoise.minimum = 36.97527026411837
config.measure_aperture_correction.numSigmaClip = 3.7130223492394188
config.measure_aperture_correction.numIter      = int(5)

# PSF Normalized Calibration Flux (N.C.F.) selector S/N
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector["science"].signalToNoise.minimum = 22.322792002973504
