# CalibrateImage → AstrometryTask tuning for difficult seeds
a = config.astrometry

# --- use brighter stars for the initial match ---
a.sourceSelector.name = "science"
ss = a.sourceSelector["science"]
ss.doSignalToNoise = True
ss.signalToNoise.minimum = 20.0          # try 15–25; raise later once stable
ss.signalToNoise.maximum = None
ss.signalToNoise.fluxField = "slot_CalibFlux_instFlux"
ss.signalToNoise.errField  = "slot_CalibFlux_instFluxErr"
# keep the defaults from setDefaults (good flag 'calib_psf_candidate'); no unresolved/isolation

# --- widen the initial search; guard for version differences ---
m = a.matcher
if hasattr(m, "maxOffsetPix"):       m.maxOffsetPix = 1500     # allow big pointing error
if hasattr(m, "maxRotationDeg"):     m.maxRotationDeg = 5.0    # tolerate rotation
if hasattr(m, "matcherIterations"):  m.matcherIterations = 20
if hasattr(m, "maxRefObjects"):      m.maxRefObjects = 20000
if hasattr(m, "maxStars"):           m.maxStars = 6000
if hasattr(m, "minMatchPairs"):      m.minMatchPairs = 8
if hasattr(m, "numPointsForShape"):  m.numPointsForShape = 6

# --- relax convergence criteria for the first pass ---
a.maxMeanDistanceArcsec = 120.0       # was 60
a.matchDistanceSigma    = 10.0        # was 8
a.maxIter               = 20

# If some visits have *good* header WCS, forcing it can help. Leave False by default.
# a.forceKnownWcs = True
