# Relax the pessimisticB matcher 
m = config.astrometry.matcher  # MatchPessimisticBConfig

# Allow larger header-WCS error and give the loop more room to converge
m.maxOffsetPix = 250          # pixels (≈ half a chip width is a good, safe start)
m.maxRotationDeg = 2.0           # degrees
m.matcherIterations = 10         # allow more shrink/soften iterations

# Demand a tighter final radius and more consensus before accepting:
m.minMatchDistPixels = 1.5      
m.minMatchedPairs = 15          
m.minFracMatchedPairs = 0.05    
m.numPatternConsensus = 3       

# Be a bit more permissive about accepting a solution
m.minMatchedPairs = 8
m.minFracMatchedPairs = 0.02

# Keep more candidates available
m.numBrightStars = 200         
m.maxRefObjects = 6000          
m.numPatternConsensus = 2

# Mild source S/N cut for the astrometry stage
ss = config.astrometry.sourceSelector["science"]
ss.doSignalToNoise = True
ss.signalToNoise.minimum = 10.0
