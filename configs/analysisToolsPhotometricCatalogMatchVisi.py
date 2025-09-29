import os

OBS_DIR = os.path.dirname(__file__)

# Use your PS1 dataset type (adjust if yours is different)
config.connections.refCatalog = "panstarrs1_dr2"

# Enable and load your colorterms
config.referenceCatalogLoader.doApplyColorTerms = True
config.referenceCatalogLoader.colorterms.load(os.path.join(OBS_DIR, "colorterms.py"))

# Load the filter map into the *refObjLoader* (this is where the task looks)
config.referenceCatalogLoader.refObjLoader.load(os.path.join(OBS_DIR, "filterMap.py"))
