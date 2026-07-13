# ruff: noqa: F821
# instrument_defaults/configs/calibrateImage/neutral_default.py
#
# NEUTRAL FRAMEWORK DEFAULT for calibrateImage, used by science.py when the
# instrument ships no tuned config of its own. It applies NO instrument tuning
# (thresholds, PSF sizes, selection) — only the measurement-schema settings
# required for the rest of stage1 to consume calibrateImage's outputs:
# standardizeSingleVisitStar's column list expects the full DRP aperture-flux
# ladder, but the stock CalibrateImageConfig measures only radius 12.0, so a
# bare stock run fails downstream with "Column base_CircularApertureFlux_*
# not available in parquet file" (found by CTIO E2E testing).
config.star_measurement.plugins.names |= [
    "base_CircularApertureFlux",
    "base_LocalBackground",
    "base_PsfFlux",
    "base_SdssCentroid",
    "base_SdssShape",
    "base_PixelFlags",
    "base_Variance",
    "base_Blendedness",
    "base_Jacobian",
]
config.star_measurement.plugins["base_CircularApertureFlux"].radii = [
    3.0,
    6.0,
    9.0,
    12.0,
    17.0,
    25.0,
    35.0,
    50.0,
    70.0,
]
config.star_measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0
config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]
config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
try:
    config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
except Exception:
    pass
