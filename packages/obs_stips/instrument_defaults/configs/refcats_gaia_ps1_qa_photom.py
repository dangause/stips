# ruff: noqa: F821
# instrument_defaults/configs/refcats_gaia_ps1_qa_photom.py
#
# NEUTRAL FRAMEWORK DEFAULT. Overlay for the visit-level PHOTOMETRIC ref-match
# QA task (analysis_tools PhotometricCatalogMatchVisitTask) switching its
# reference catalog from MONSTER to PS1 DR2. Applied via --config-file by
# science.py ONLY when refcat.mode == "gaia_ps1". The band->PS1-column map is
# derived from the active profile's ps1_band_map, exactly like the
# calibrateImage overlay (refcats_gaia_ps1.py). Color terms are left off for
# the neutral QA tier; an instrument can override with its own copy under
# instruments/<name>/configs/.
import json
import os

config.connections.refCat = "panstarrs1_dr2"
# Band map via env (see refcats_gaia_ps1.py for why importing the profile
# inside a pex_config file breaks quantum-graph reloading).
_ps1_band_map = json.loads(os.environ.get("STIPS_PS1_BAND_MAP", "{}"))
if not _ps1_band_map:
    from lsst.obs.stips.profile_loader import load_profile_from_dir

    _ps1_band_map = dict(
        load_profile_from_dir(os.environ["INSTRUMENT_DIR"]).ps1_band_map
    )
# The matcher looks up reference fluxes by PHYSICAL filter as well as by band
# (e.g. Y4KCam physical 'I' for band 'i'), so map both spellings. Instruments
# whose physical filter names are not simply the upper-cased band should ship
# their own copy of this overlay under instruments/<name>/configs/.
config.referenceCatalogLoader.refObjLoader.filterMap = {
    key: f"{ps1_band}MeanPSFMag"
    for band, ps1_band in _ps1_band_map.items()
    for key in (band, band.upper())
}
config.referenceCatalogLoader.doApplyColorTerms = False
