# ruff: noqa: F821
# instrument_defaults/configs/apply_colorterms.py
#
# NEUTRAL FRAMEWORK DEFAULT. Injected into calibrateImage at runtime via
# ``--config-file calibrateImage:<this file>`` (science.py). Turns color terms ON
# *only* when the active instrument actually ships a color-term library -- an
# empty library with ``applyColorTerms=True`` raises a FieldValidationError in
# the stack (see the neutral colorterms.py header).
#
# Color-term libraries are per-telescope empirical fits, so this file loads the
# ACTIVE instrument's ``configs/colorterms.py`` (via $INSTRUMENT_DIR, exported by
# run_with_stack and the pipeline-graph test) in preference to the empty neutral
# library co-located here. The reference Nickel fit lives at
# ``instruments/nickel/configs/colorterms.py`` and is picked up automatically.
import os

config_dir = os.path.dirname(__file__)

# Prefer the active instrument's colorterms.py; fall back to the empty neutral
# library shipped next to this file.
_instrument_dir = os.environ.get("INSTRUMENT_DIR")
_colorterms_path = os.path.join(config_dir, "colorterms.py")
if _instrument_dir:
    _candidate = os.path.join(_instrument_dir, "configs", "colorterms.py")
    if os.path.isfile(_candidate):
        _colorterms_path = _candidate

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
config.photometry.colorterms.load(_colorterms_path)

# Enable color terms only when the resolved library is non-empty. A fork with no
# colorterms.py inherits the empty neutral library and calibrates with a plain
# per-visit zeropoint (no color correction) instead of failing config validation.
config.photometry.applyColorTerms = len(config.photometry.colorterms.data) > 0
