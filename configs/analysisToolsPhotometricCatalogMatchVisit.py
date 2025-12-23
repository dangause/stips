import os

OBS_DIR = os.path.dirname(__file__)

# PS1 refcat dataset type (adjust if yours has a date suffix)
config.connections.refCatalog = "the_monster_20250219_local"

# Enable color terms and load your existing library
config.referenceCatalogLoader.doApplyColorTerms = True
config.referenceCatalogLoader.colorterms.load(os.path.join(OBS_DIR, "colorterms.py"))

# Load a band-letter filter map for Nickel
config.referenceCatalogLoader.refObjLoader.load(os.path.join(OBS_DIR, "filter_map.py"))
