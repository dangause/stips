# # Tighter astrometry once WCS is roughly correct

# configs/astrometry_strict_postFlip.py
m = config.astrometry.matcher
m.maxOffsetPix = 40          # small search box now that parity is corrected
m.maxRotationDeg = 0.5
m.matcherIterations = 8
m.minMatchedPairs = 15
m.minMatchDistPixels = 1.5


# m = config.astrometry.matcher
# m.maxOffsetPix = 150            # small search box when headers are good
# m.maxRotationDeg = 0.5
# m.matcherIterations = 12
# m.minMatchDistPixels = 2.0

# # Demand stronger consensus
# m.minMatchedPairs = 30
# m.minFracMatchedPairs = 0.08
# m.numPatternConsensus = 3

# m.numBrightStars = 120
# m.maxRefObjects  = 8000

# # Science source selector (keep dependency-free)
# ss = config.astrometry.sourceSelector["science"]
# ss.doUnresolved = False
# ss.doFlags = True
# ss.flags.bad = [
#     "base_PixelFlags_flag_edge",
#     "base_PixelFlags_flag_interpolatedCenter",
#     "base_PixelFlags_flag_saturatedCenter",
#     "base_PixelFlags_flag_crCenter",
# ]
# ss.doIsolated = False
# ss.doSignalToNoise = True
# ss.signalToNoise.fluxField = "base_PsfFlux_instFlux"
# ss.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
# ss.signalToNoise.minimum   = 30.0
# # Fallback:
# # ss.signalToNoise.fluxField = "base_GaussianFlux_instFlux"
# # ss.signalToNoise.errField  = "base_GaussianFlux_instFluxErr"

# # Reference selector (Gaia DR3: no 'flux' alias)
# refSel = config.astrometry.referenceSelector
# refSel.doMagLimit = False
