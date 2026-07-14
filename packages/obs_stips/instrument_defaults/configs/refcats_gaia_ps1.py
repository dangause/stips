# ruff: noqa: F821
# instrument_defaults/configs/refcats_gaia_ps1.py
#
# NEUTRAL FRAMEWORK DEFAULT. calibrateImage overlay that switches the reference
# catalogs from MONSTER (the DRP.yaml default) to Gaia DR3 (astrometry) + PS1 DR2
# (photometry). Applied via --config-file by science.py ONLY when
# refcat.mode == "gaia_ps1".
#
# The Gaia astrometry setup is instrument-neutral. The PS1 photometry filterMap
# is DERIVED from the active instrument profile's ``ps1_band_map`` (LOCAL band ->
# PS1 band), so a fork inherits a correct r/i map with no per-instrument file.
# Bands with no PS1 equivalent (e.g. Nickel/CTIO b/v/u) are calibrated purely via
# color terms and are NOT in ps1_band_map; a fork that needs explicit
# columns/color handling for those should drop its own ``refcats_gaia_ps1.py``
# into ``instruments/<name>/configs/`` (resolved instrument-dir-first). The
# reference Nickel overlay (full b/v/r/i/halpha/oiii/gp/rp map + Landolt color
# terms) lives at ``instruments/nickel/configs/refcats_gaia_ps1.py``.
import json
import os

# ---- Astrometry: Gaia DR3 (single-flux astrometric reference) ----
config.connections.astrometry_ref_cat = "gaia_dr3"
# Gaia is single-flux: map every science band to the Gaia G flux. This is the
# CalibrateImageConfig default, but we set it explicitly to override the
# MONSTER filterMap baked into DRP.yaml.
config.astrometry_ref_loader.anyFilterMapsToThis = "phot_g_mean"
config.astrometry_ref_loader.filterMap = {}
# Tuned configs may set the astrometric mag-limit flux field to a MONSTER column;
# point it at the Gaia G flux so the selector finds it.
config.astrometry.referenceSelector.magLimit.fluxField = "phot_g_mean_flux"

# ---- Photometry: PS1 DR2 (per-band flux + color terms) ----
config.connections.photometry_ref_cat = "panstarrs1_dr2"
# Derive the LOCAL band -> PS1 mean-PSF magnitude column map from the profile,
# via the STIPS_PS1_BAND_MAP env var exported by run_with_stack. Do NOT import
# the profile here: pex_config replays modules imported during config exec when
# a saved quantum graph is reloaded, and the path-loaded profile machinery
# ("fetch") cannot be imported at replay time.
_instrument_dir = os.environ["INSTRUMENT_DIR"]
_ps1_band_map = json.loads(os.environ.get("STIPS_PS1_BAND_MAP", "{}"))
if not _ps1_band_map:
    # Fallback for direct pipetask use outside STIPS (no env var): load the
    # profile. Safe at graph-BUILD time; a graph saved this way cannot be
    # re-loaded outside a matching sys.path (see above).
    from lsst.obs.stips.profile_loader import load_profile_from_dir

    _ps1_band_map = dict(load_profile_from_dir(_instrument_dir).ps1_band_map)
config.photometry_ref_loader.filterMap = {
    band: f"{ps1_band}MeanPSFMag" for band, ps1_band in _ps1_band_map.items()
}
config.photometry.photoCatName = "ps1"

# Load the active instrument's color-term library if it ships one; enable color
# terms only when non-empty (an empty library with applyColorTerms=True fails
# config validation).
_colorterms_path = os.path.join(_instrument_dir, "configs", "colorterms.py")
if not os.path.isfile(_colorterms_path):
    _colorterms_path = os.path.join(os.path.dirname(__file__), "colorterms.py")
config.photometry.colorterms.load(_colorterms_path)
config.photometry.applyColorTerms = len(config.photometry.colorterms.data) > 0
