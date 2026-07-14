# ============================================================================
# NEUTRAL FRAMEWORK DEFAULT -- EMPTY COLOR-TERM LIBRARY.
#
# Color terms convert a reference catalog's magnitudes (PS1, Gaia, MONSTER, ...)
# into an instrument's native photometric system. They are EMPIRICALLY FIT per
# telescope (against Landolt/standard fields) and are therefore NOT generic:
# shipping one instrument's fit as the framework default would silently
# mis-calibrate every fork's photometry.
#
# This default is intentionally EMPTY. A fork that wants color-term corrections
# must drop its own ``colorterms.py`` into ``instruments/<name>/configs/`` (it is
# resolved instrument-dir-first). The reference Nickel fit now lives at
# ``instruments/nickel/configs/colorterms.py``.
#
# The generic consumers of this file (apply_colorterms.py,
# analysisToolsPhotometricCatalogMatchVisit.py) detect an empty library and
# leave ``applyColorTerms`` OFF so the graph still validates -- an empty library
# with ``applyColorTerms=True`` raises a FieldValidationError in the stack.
# ============================================================================
# ruff: noqa: F821
from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict  # noqa: F401

config.data = {}
