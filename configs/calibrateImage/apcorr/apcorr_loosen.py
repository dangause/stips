# Tighter astrometry when headers/WCS are roughly correct.

m = config.astrometry.matcher
m.maxOffsetPix       = 150
m.maxRotationDeg     = 0.5
m.matcherIterations  = 12
m.minMatchDistPixels = 2.0
m.minMatchedPairs      = 30
m.minFracMatchedPairs  = 0.08
m.numPatternConsensus  = 3
m.numBrightStars = 120
m.maxRefObjects  = 8000

ss = config.astrometry.sourceSelector["science"]
ss.doUnresolved = False
ss.doIsolated   = False
ss.doFlags      = True
ss.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
]
ss.doSignalToNoise = True
ss.signalToNoise.fluxField = "base_PsfFlux_instFlux"
ss.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
ss.signalToNoise.minimum   = 30.0

refSel = config.astrometry.referenceSelector
refSel.doMagLimit = False
