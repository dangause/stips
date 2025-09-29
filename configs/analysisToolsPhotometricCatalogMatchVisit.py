import os

OBS_DIR = os.path.dirname(__file__)

# PS1 refcat dataset type (adjust if yours has a date suffix)
config.connections.refCatalog = "the_monster_20250219_local"

# Enable color terms and load your existing library
config.referenceCatalogLoader.doApplyColorTerms = True
config.referenceCatalogLoader.colorterms.load(os.path.join(OBS_DIR, "colorterms.py"))

# Load a band-letter filter map for Nickel
# (don't assign column-name strings like gMeanPSFMag here)
config.referenceCatalogLoader.refObjLoader.load(os.path.join(OBS_DIR, "filterMap.py"))


# # $OBS_NICKEL/configs/analysisToolsPhotometricCatalogMatchVisit.py
# import os
# OBS_DIR = os.path.dirname(__file__)

# # --- Reference loader band mapping → creates aliases like i_flux → monster_ComCam_i_flux
# config.refLoader.filterMap = {
#     # accept both lowercase and uppercase Nickel bands
#     "b": "monster_ComCam_g",
#     "v": "monster_ComCam_g",
#     "r": "monster_ComCam_r",
#     "i": "monster_ComCam_i",
#     "B": "monster_ComCam_g",
#     "V": "monster_ComCam_g",
#     "R": "monster_ComCam_r",
#     "I": "monster_ComCam_i",
# }

# # sensible default if an unmapped band is encountered
# config.refLoader.anyFilterMapsToThis = "monster_ComCam_g"

# # --- color terms (to keep analysis-tools consistent with calibrateImage)
# config.applyColorTerms = True
# config.photoCatName = "the_monster_20250219_local"
# # use the same colorterms library you already created
# config.colorterms.load(os.path.join(OBS_DIR, "colorterms.py"))
