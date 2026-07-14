"""Butler dataset-type name constants shared across STIPS core modules.

The LSST Science Pipelines occasionally rename dataset types across stack
versions (e.g. ``goodSeeingDiff_differenceExp`` became ``difference_image``).
When those strings are duplicated as bare literals throughout ``core/`` a rename
means hunting every call site -- and the dashboard has already drifted out of
sync this way. Centralizing them here makes a future rename a single edit.

See finding F-025 (version-coupling) in ``docs/audit/findings-2026-07-10.md``
and the accompanying ``docs/stack-bump-runbook.md``.
"""

from __future__ import annotations

# --- Difference imaging (core/dia.py, core/fphot.py) ---------------------------
#: Per-visit difference image produced by the DIA pipeline.
DIFFERENCE_IMAGE = "difference_image"
#: Unfiltered DIA source catalog measured on the difference image.
DIA_SOURCE_UNFILTERED = "dia_source_unfiltered"

# --- Coadd templates (core/coadd.py) -------------------------------------------
#: Deep coadd used as the DIA template.
TEMPLATE_COADD = "template_coadd"
#: Preliminary per-visit calibrated image (input to warping/coaddition).
PRELIMINARY_VISIT_IMAGE = "preliminary_visit_image"

# --- Forced photometry at RA/Dec (core/lightcurve.py selection, tools) ---------
#: Forced photometry measured at fixed RA/Dec on the difference image.
FORCED_PHOT_DIFFIM_RADEC = "forced_phot_diffim_radec"
#: Forced photometry measured at fixed RA/Dec on the direct (visit) image.
FORCED_PHOT_RADEC = "forced_phot_radec"
#: Legacy alias for the diffim forced-phot table.
FORCED_DIFF_RADEC = "forced_diff_radec"

#: Prefix shared by the forced-photometry dataset types above. ``core/run.py``
#: routes lightcurve sourcing by testing this prefix, so keep it in sync.
FORCED_PHOT_PREFIX = "forced_phot"
