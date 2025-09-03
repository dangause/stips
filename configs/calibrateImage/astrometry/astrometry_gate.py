# configs/astrometry_gate.py
a = config.astrometry

# Robust pruning during the iterative fit
a.doMagnitudeOutlierRejection = True
a.magnitudeOutlierRejectionNSigma = 2.5

# Tighten the distance envelope a bit, allow a couple extra fit cycles
a.matchDistanceSigma = 1.5
a.maxIter = 5

# Hard fail if the final solution is too sloppy
a.maxMeanDistanceArcsec = 0.8   # pick 0.6–0.8″ to taste

# Leave matcher mostly at defaults; only tighten endgame
m = a.matcher
m.minMatchDistPixels = 1.5
