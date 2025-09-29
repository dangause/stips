# obs_nickel/configs/apply_colorterms.py
import os

config_dir = os.path.dirname(__file__)

# turn on color terms
config.photometry.applyColorTerms = True

# choose which colorterm block to use, based on the refcat the pipeline is using
refname = getattr(config.connections, "photometry_ref_cat", None) or "panstarrs1_dr2"

# normalize to keys in colorterms.py
alias = {
    "panstarrs1_dr2": "ps1",
    "gaia_dr3": "gaia",
    "the_monster_20250219_local": "monster",
}
config.photometry.photoCatName = alias.get(refname, refname)

# load the library defining config.data = {...}
config.photometry.colorterms.load(os.path.join(config_dir, "colorterms.py"))
