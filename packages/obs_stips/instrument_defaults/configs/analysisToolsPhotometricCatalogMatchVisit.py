# ruff: noqa: F821
# instrument_defaults/configs/analysisToolsPhotometricCatalogMatchVisit.py
#
# NEUTRAL FRAMEWORK DEFAULT for the visit-level photometric ref-cat match QA task
# (analysis_tools PhotometricCatalogMatchVisitTask). Loaded by
# analysis-visit-single-visit.yaml via $STIPS_DEFAULTS/configs/.
#
# Color terms and the band->refcat-column filter map are per-telescope, so this
# file loads the ACTIVE instrument's ``configs/{colorterms,filter_map}.py``
# (via $INSTRUMENT_DIR) in preference to the co-located neutral defaults.
# doApplyColorTerms is enabled ONLY when the resolved colorterm library is
# non-empty -- an empty library with doApplyColorTerms=True raises a
# FieldValidationError at graph-build time.
import os

OBS_DIR = os.path.dirname(__file__)
_instrument_dir = os.environ.get("INSTRUMENT_DIR")

# Resolve each dependency instrument-dir-first, else the neutral default
# co-located here. (Inline, not a helper function: pex_config executes this file
# with separate exec scopes, so module-level names are invisible inside nested
# function bodies.)
_filter_map_path = os.path.join(OBS_DIR, "filter_map.py")
_colorterms_path = os.path.join(OBS_DIR, "colorterms.py")
if _instrument_dir:
    _candidate = os.path.join(_instrument_dir, "configs", "filter_map.py")
    if os.path.isfile(_candidate):
        _filter_map_path = _candidate
    _candidate = os.path.join(_instrument_dir, "configs", "colorterms.py")
    if os.path.isfile(_candidate):
        _colorterms_path = _candidate

# Refcat dataset type (adjust if yours has a date suffix)
config.connections.refCatalog = "the_monster_20250219_local"

# Load the band-letter filter map (instrument override, else neutral reference map)
config.referenceCatalogLoader.refObjLoader.load(_filter_map_path)

# Load the color-term library (instrument fit, else empty neutral library) and
# enable color terms only if it is non-empty.
config.referenceCatalogLoader.colorterms.load(_colorterms_path)
config.referenceCatalogLoader.doApplyColorTerms = (
    len(config.referenceCatalogLoader.colorterms.data) > 0
)
