# configs/astrometry_relax_for_failures.py
a = config.astrometry
a.doMagnitudeOutlierRejection = True
a.magnitudeOutlierRejectionNSigma = 2.5
a.matchDistanceSigma = 1.5
a.maxIter = 5
a.maxMeanDistanceArcsec = 0.8    # same safety rail

m = a.matcher
m.maxOffsetPix = 600             # a bit wider box, not 1500
m.maxRotationDeg = 2.0
m.matcherIterations = 8
m.minMatchedPairs = 12
m.minFracMatchedPairs = 0.04
m.minMatchDistPixels = 2.0
