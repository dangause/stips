# calibrateImage: MeasureApCorr selector + model
c = config.measure_aperture_correction
c.sourceSelector.name = "science"
ss = c.sourceSelector["science"]
ss.doFlags = True
ss.flags.good = ["calib_psf_used"]
ss.flags.bad = []
ss.doUnresolved = False          # <-- keep False here
ss.doIsolated = False
ss.doSignalToNoise = True
ss.signalToNoise.minimum = 30.0
ss.signalToNoise.maximum = None
ss.signalToNoise.fluxField = "base_PsfFlux_instFlux"
ss.signalToNoise.errField  = "base_PsfFlux_instFluxErr"

c.fitConfig.orderX = 0
c.fitConfig.orderY = 0
c.numSigmaClip = 5.0
c.numIter = 4
c.allowFailure = ["base_GaussianFlux"]

# PSF normalized calibration flux selector (this is where it crashed)
ncf = config.psf_normalized_calibration_flux.measure_ap_corr
ncf.sourceSelector.name = "science"
nss = ncf.sourceSelector["science"]
nss.doSignalToNoise = True
nss.signalToNoise.minimum = 25.0
nss.doUnresolved = False         # <-- set False here too
nss.doIsolated = False
