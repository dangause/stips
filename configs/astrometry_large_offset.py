# Coarse astrometry to recover from ~1-chip header WCS errors

m = config.astrometry.matcher  # lsst.meas.astrom.matchPessimisticB.MatchPessimisticBConfig
m.maxOffsetPix = 1100          # allow ~full-detector shift
m.maxRotationDeg = 1.5
m.matcherIterations = 18
m.minMatchDistPixels = 2.5

# Be permissive but keep a real geometric consensus
m.minMatchedPairs = 25
m.minFracMatchedPairs = 0.05
m.numPatternConsensus = 3

# Candidate pools
m.numBrightStars = 180
m.maxRefObjects  = 12000

# --- Science source selector (NO deblend/classifier dependencies) ---
ss = config.astrometry.sourceSelector["science"]
ss.doUnresolved = False            # don't require classification fields
ss.doFlags = True
ss.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
]
ss.doIsolated = False              # no deblend_nChild in these catalogs
ss.doSignalToNoise = True
ss.signalToNoise.fluxField = "base_PsfFlux_instFlux"       # or Gaussian if PSF absent
ss.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
ss.signalToNoise.minimum   = 25.0
# ss.signalToNoise.fluxField = "base_GaussianFlux_instFlux"
# ss.signalToNoise.errField  = "base_GaussianFlux_instFluxErr"

# --- Reference selector (Gaia DR3: no 'flux' alias) ---
refSel = config.astrometry.referenceSelector
refSel.doMagLimit = False          # avoid KeyError: 'flux'

# Optional: if you *really* want a mag cut with Gaia, set a real column:
# refSel.doMagLimit = True
# refSel.magLimit.fluxField = "phot_g_mean_flux"  # Gaia-specific
# refSel.magLimit.minimum = 12.0                  # but these are MAG cuts
# refSel.magLimit.maximum = 18.5                  # you'd need to convert to flux units

# Optional: prefer a specific refcat (already used in your logs)
# config.astrometry.refObjLoader.ref_dataset_name = "gaia_dr3_20250728"
