# ruff: noqa: F821
# instrument_defaults/configs/refcats_gaia_ps1.py
#
# calibrateImage overlay that switches the reference catalogs from MONSTER
# (the DRP.yaml default) to Gaia DR3 (astrometry) + PS1 DR2 (photometry).
#
# Applied via --config-file by science.py ONLY when refcat.mode == "gaia_ps1".
# Self-contained: sets photoCatName + loads colorterms here so it does not depend
# on apply_colorterms.py running after it.
#
# After validation on real data, this becomes the DRP.yaml default and a
# refcats_monster.py overlay handles the opt-in MONSTER path instead.
import os

# ---- Astrometry: Gaia DR3 (single-flux astrometric reference) ----
config.connections.astrometry_ref_cat = "gaia_dr3"
# Gaia is single-flux: map every science band to the Gaia G flux. This is the
# CalibrateImageConfig default, but we set it explicitly to override the
# MONSTER filterMap baked into DRP.yaml.
config.astrometry_ref_loader.anyFilterMapsToThis = "phot_g_mean"
config.astrometry_ref_loader.filterMap = {}

# ---- Photometry: PS1 DR2 (per-band flux + color terms) ----
config.connections.photometry_ref_cat = "panstarrs1_dr2"
# Map Nickel bands to PS1 mean-PSF magnitude columns. b/v have no native PS1
# filter and are calibrated entirely via the PS1 g/r color terms below.
config.photometry_ref_loader.filterMap = {
    "b": "gMeanPSFMag",
    "v": "gMeanPSFMag",
    "r": "rMeanPSFMag",
    "i": "iMeanPSFMag",
    "halpha": "rMeanPSFMag",
    "oiii": "gMeanPSFMag",
    "gp": "gMeanPSFMag",
    "rp": "rMeanPSFMag",
}
config.photometry.applyColorTerms = True
# "ps1" matches the "ps1*" block in colorterms.py (kept consistent with the
# alias in apply_colorterms.py).
config.photometry.photoCatName = "ps1"

_config_dir = os.path.dirname(os.path.abspath(__file__))
config.photometry.colorterms.load(os.path.join(_config_dir, "colorterms.py"))
