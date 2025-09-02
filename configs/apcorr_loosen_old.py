# Loosen star selection for aperture corrections on sparse frames and
# use robust INSTFLUX fields present in the catalogs.

# ---- Main aperture-correction step ----
config.measure_aperture_correction.sourceSelector.name = "science"
sel = config.measure_aperture_correction.sourceSelector["science"]

sel.doFlags = True
sel.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
]
sel.doIsolated = False
sel.doUnresolved = False

sel.doSignalToNoise = True
sel.signalToNoise.fluxField = "base_PsfFlux_instFlux"
sel.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
sel.signalToNoise.minimum   = 5.0

# ---- PSF-normalized calibration flux's own apcorr step ----
config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector.name = "science"
sel2 = config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector["science"]

sel2.doFlags = True
sel2.flags.bad = sel.flags.bad
sel2.doIsolated = False
sel2.doUnresolved = False

sel2.doSignalToNoise = True
sel2.signalToNoise.fluxField = "base_PsfFlux_instFlux"
sel2.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
sel2.signalToNoise.minimum   = 5.0

# If your schema lacks PSF instFlux, swap both blocks to Gaussian instFlux:
# *_signalToNoise.fluxField = "base_GaussianFlux_instFlux"
# *_signalToNoise.errField  = "base_GaussianFlux_instFluxErr"

# As an emergency fallback (not recommended for final science), you can
# disable S/N cuts entirely:
# sel.doSignalToNoise = False
# sel2.doSignalToNoise = False
