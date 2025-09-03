# Use the object-size selector with looser cuts
cfg = config.psf_measure_psf.starSelector["objectSize"]
cfg.doSignalToNoiseLimit = True
cfg.signalToNoiseMin = 10.0            # was 50
cfg.doFluxLimit = False                # drop the 12.5k flux floor
cfg.widthMin = 0.8
cfg.widthMax = 8.0
cfg.widthStdAllowed = 0.40             # widen cluster tolerance
cfg.nSigmaClip = 3.0

# Be a bit less strict on mask flags for sparse frames
cfg.badFlags = [
    "base_PixelFlags_flag_edge",
    "base_PixelFlags_flag_saturatedCenter",
    "base_PixelFlags_flag_crCenter",
    "base_PixelFlags_flag_bad",
    "slot_Centroid_flag",
]

# Don’t reserve any stars when star-poor
config.psf_measure_psf.reserve.fraction = 0.0

# Make PSFEx cheaper spatially
config.psf_measure_psf.psfDeterminer["psfex"].spatialOrder = 1

# # Quiet WCS-needed plugin during PSF stage
# config.psf_source_measurement.plugins = [
#     "base_PixelFlags","base_SdssCentroid",
#     "base_CircularApertureFlux","base_GaussianFlux","base_PsfFlux"
# ]
