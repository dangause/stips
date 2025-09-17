# obs_nickel/configs/apply_colorterms.py
import os

config_dir = os.path.dirname(__file__)

# turn on color terms
config.photometry.applyColorTerms = True

# ensure PhotoCal knows which colorterm block to use
refname = getattr(config.connections, "photometry_ref_cat", None)
if not refname:
    # fall back if your tuned config doesn’t set it
    refname = "panstarrs1_dr2_20250911"  # or "gaia_dr3_20250728"
config.photometry.photoCatName = refname

# load your library (generated colorterms.py that sets config.data = {...})
config.photometry.colorterms.load(os.path.join(config_dir, "colorterms.py"))
