# ruff: noqa: F821
# FGCM reference loader configuration for Nickel
# Applies color terms using the existing obs_nickel colorterms.py library

import os

config.fgcmLoadReferenceCatalog.filterMap = {
    "b": "monster_ComCam_g",
    "v": "monster_ComCam_g",
    "r": "monster_ComCam_r",
    "i": "monster_ComCam_i",
}
config.fgcmLoadReferenceCatalog.applyColorTerms = True
config.fgcmLoadReferenceCatalog.colorterms.load(
    os.path.join(os.path.dirname(__file__), "colorterms.py")
)
