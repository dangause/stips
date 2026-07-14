# ruff: noqa: F821
# instrument_defaults/configs/refcats_gaia_ps1_qa_astrom.py
#
# NEUTRAL FRAMEWORK DEFAULT. Overlay for the visit-level ASTROMETRIC ref-match
# QA task (analysis_tools AstrometricCatalogMatchVisitTask) switching its
# reference catalog from MONSTER (the pipeline default) to Gaia DR3. Applied
# via --config-file by science.py ONLY when refcat.mode == "gaia_ps1", so the
# QA matches against the same catalog the astrometric calibration used —
# and fields outside the local MONSTER shard coverage still get QA.
config.connections.refCatalog = "gaia_dr3"
# Gaia is single-flux: every science band maps to the G flux.
config.referenceCatalogLoader.refObjLoader.anyFilterMapsToThis = "phot_g_mean"
config.referenceCatalogLoader.refObjLoader.filterMap = {}
config.referenceCatalogLoader.doApplyColorTerms = False
