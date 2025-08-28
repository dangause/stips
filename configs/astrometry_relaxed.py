# Relax the pessimisticB matcher (names are in PIXELS/DEGREES here)
m = config.astrometry.matcher  # MatchPessimisticBConfig

# Allow larger header-WCS error and give the loop more room to converge
m.maxOffsetPix = 1500          # pixels (≈ half a chip width is a good, safe start)
m.maxRotationDeg = 5.0           # degrees
m.matcherIterations = 15         # allow more shrink/soften iterations

# Keep pairs alive near the end of shrinking
m.minMatchDistPixels = 3.0       # floor on match radius (in pixels)

# Be a bit more permissive about accepting a solution
m.minMatchedPairs = 8
m.minFracMatchedPairs = 0.02

# Keep more candidates available
m.numBrightStars = 300
m.maxRefObjects = 10000
m.numPatternConsensus = 2

# Mild source S/N cut for the astrometry stage
ss = config.astrometry.sourceSelector["science"]
ss.doSignalToNoise = True
ss.signalToNoise.minimum = 10.0
