import os

OBS_DIR = os.path.dirname(__file__)

# Use your PS1 refcat dataset type (must be registered in Butler)
config.connections.refCatalog = "panstarrs1_dr2"

# Apply color terms and load your existing colorterms.py
config.referenceCatalogLoader.doApplyColorTerms = True
config.referenceCatalogLoader.colorterms.load(os.path.join(OBS_DIR, "colorterms.py"))

# Map Nickel physical_filter -> PS1 column names used in your colorterms
# (keys must match the physical_filter strings in your repo)
config.referenceCatalogLoader.refObjLoader.filterMap = dict(
    B="gMeanPSFMag",
    V="gMeanPSFMag",
    R="rMeanPSFMag",
    I="iMeanPSFMag",
)
