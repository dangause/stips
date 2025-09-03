# configs/calibrateImage/apcorr/apcorr_loosen_minimal.py
# Make aperture-correction source selection permissive, and use a flux
# that we know exists in calibrateImage catalogs.
# configs/calibrateImage/apcorr/apcorr_loosen_minimal.py
# Loosen selection for aperture-correction steps, using GaussianFlux for S/N.

# ---- PSF-normalized calibration flux (normalizedCalibrationFlux) ----
selN = config.psf_normalized_calibration_flux.measure_ap_corr.sourceSelector["science"]
selN.doFlags = True
selN.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_crCenter",
]
selN.doSignalToNoise = True
selN.signalToNoise.minimum = 8.0
selN.signalToNoise.fluxField = "base_PsfFlux_instFlux"
selN.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
# Be permissive; some visits lack these diagnostics/columns
selN.doIsolated   = False
selN.doUnresolved = False

# ---- Main aperture-correction task (MeasureApCorrTask) ---------------
selM = config.measure_aperture_correction.sourceSelector["science"]
selM.doFlags = True
selM.flags.bad = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_interpolatedCenter",
    "base_PixelFlags_flag_crCenter",
]
selM.doSignalToNoise = True
selM.signalToNoise.minimum = 8.0
selM.signalToNoise.fluxField = "base_PsfFlux_instFlux"
selM.signalToNoise.errField  = "base_PsfFlux_instFluxErr"
selM.doIsolated   = False
selM.doUnresolved = False
