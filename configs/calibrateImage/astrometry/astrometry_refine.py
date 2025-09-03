# Tight astrometry once coarse pass has recovered the pointing
m = config.astrometry.matcher

m.maxOffsetPix = 120           # now expect small residual shifts
m.maxRotationDeg = 0.5
m.matcherIterations = 12
m.minMatchDistPixels = 1.5

m.minMatchedPairs = 25
m.minFracMatchedPairs = 0.05
m.numPatternConsensus = 3

m.numBrightStars = 180
m.maxRefObjects  = 8000

ss = config.astrometry.sourceSelector["science"]
ss.doUnresolved = True
ss.doFlags = True
ss.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
]
ss.doIsolated = True
ss.doSignalToNoise = True
ss.signalToNoise.minimum = 20.0
ss.signalToNoise.fluxField = "base_PsfFlux_flux"

refSel = config.astrometry.referenceSelector
refSel.doMagLimit = True
refSel.magLimit.minimum = 12.0
refSel.magLimit.maximum = 19.0

# Prefer Gaia if available:
# config.astrometry.refObjLoader.ref_dataset_name = "gaia_dr3_20xx_xx"
