# Even-more-permissive “salvage” astrometry for large header WCS errors.

# 1) Load *more* reference objects around the exposure
#    This is key when the header WCS can be off by ~ a detector or more.
#    (pixelMargin expands the sky box before transforming to RA/Dec)
config.astrometry.refObjLoader.pixelMargin = 3000

# If you want to use PS1 positions for astrometry instead of Gaia, uncomment:
# config.astrometry.refObjLoader.ref_dataset_name = "panstarrs1_dr2_20250730"

# 2) Matcher settings (MatchPessimisticB)
m = config.astrometry.matcher
m.maxOffsetPix       = 1500     # allow ~full-chip shift
m.maxRotationDeg     = 3.5      # small rotation errors permitted
m.matcherIterations  = 20
m.minMatchDistPixels = 2.5

# Be permissive about consensus to seed a fit, then fitter will clean:
m.minMatchedPairs       = 10
m.minFracMatchedPairs   = 0.02
m.numPatternConsensus   = 3

# Candidate pools (keep large so we don’t starve the matcher)
m.numBrightStars = 300
m.maxRefObjects  = 20000

# 3) Science source selection: keep dependency-free and reasonably bright
ss = config.astrometry.sourceSelector["science"]
ss.doUnresolved = False             # avoid classifier dependency
ss.doIsolated   = False             # avoid deblend_nChild dependency
ss.doFlags      = True
ss.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
]
ss.doSignalToNoise = True
# Prefer PSF instFlux if present; otherwise swap both lines to Gaussian instFlux.
ss.signalToNoise.fluxField = "base_PsfFlux_instFlux"
ss.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
ss.signalToNoise.minimum   = 12.0   # a bit lower for blue frames

# 4) Reference selector: disable mag cut (Gaia/PS1 may not expose a 'flux' alias)
refSel = config.astrometry.referenceSelector
refSel.doMagLimit = False
