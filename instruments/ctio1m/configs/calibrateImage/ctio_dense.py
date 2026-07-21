# ruff: noqa: F821
# CTIO 1.0m / Y4KCam — PRIMARY dense-field calibrateImage config (Cycle 2, astrometry).
#
# Geometry: 0.29"/pix, ~20' FOV, 4064x4064 assembled, 4 amps. Fitted for NGC2298
# (dense southern globular, Dec -36) against Gaia DR3 astrometry. CTIO-derived
# values (NOT ported from Nickel). Astrometry-only tuning; photometry left at
# neutral-default behavior (southern photometric-refcat story is item 3).
#
# ROOT CAUSE this config fixes (Cycle 2 finding, 2026-07-20): the neutral default
# leaves the astrometry matcher UNCAPPED. On NGC2298's dense field the matcher's
# asterism pattern construction (construct_pattern_and_shift_rot_matrix) explodes
# combinatorially over thousands of sources/refs -> a single visit did not finish
# calibrateImage in 28 min, and marginal visits fail with MatcherFailure. Capping
# the source/reference counts and demanding higher-S/N inputs breaks the blowup:
# far fewer, cleaner candidates feed the matcher, so it converges fast AND matches.
#
# Fallback chain: ctio_dense -> ctio_relaxed.

# --- measurement schema (REQUIRED; downstream stage-1 consumes the full ladder) ---
config.star_measurement.plugins.names |= [
    "base_CircularApertureFlux", "base_LocalBackground", "base_PsfFlux",
    "base_SdssCentroid", "base_SdssShape", "base_PixelFlags", "base_Variance",
    "base_Blendedness", "base_Jacobian",
    "ext_shapeHSM_HsmPsfMomentsDebiased", "ext_shapeHSM_HsmShapeRegauss",
]
config.star_measurement.plugins["base_CircularApertureFlux"].radii = [
    3.0, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0,
]
config.star_measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0
config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]
config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
try:
    config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
except Exception:
    pass

# --- detection: high threshold => far fewer sources on the dense field (speed + clean) ---
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = 8.0        # aggressive; dense field has plenty
config.psf_detection.includeThresholdMultiplier = 3.0
config.psf_detection.minPixels = 7

# --- source selection into astrometry: high S/N only (bounds matcher input count) ---
config.astrometry.sourceSelector["science"].signalToNoise.minimum = 20.0

# --- ASTROMETRY REFCAT: use Gaia DR3, not MONSTER (Cycle-2 finding 2026-07-20) ---
# The framework DRP.yaml points astrometry_ref_cat at the_monster, but calibrateImage's
# own setDefaults sets astrometry_ref_loader.anyFilterMapsToThis="phot_g_mean" (Gaia's flux
# field). MONSTER's phot_g_mean is NaN for many crowded-field sources, so the matcher's
# maxRefObjects flux-trim (_filterRefCat sorts by that field) selects ZERO -> ValueError
# "No reference objects supplied". Gaia DR3 has valid phot_g_mean everywhere and is the
# correct astrometry reference (proper motion, clean fluxes). Gaia covers NGC2298 (verified).
config.connections.astrometry_ref_cat = "gaia_dr3"
# DRP.yaml configures the astrometry loader for MONSTER (anyFilterMapsToThis=null +
# filterMap-> monster_ComCam_* columns). Switch it fully back to Gaia's phot_g_mean:
# all filters map to the single valid Gaia flux column (no NaN -> the maxRefObjects
# flux-trim works). Clear the MONSTER filterMap so it does not shadow this.
config.astrometry_ref_loader.anyFilterMapsToThis = "phot_g_mean"
config.astrometry_ref_loader.filterMap = {}

# --- reference loading margin (refcat density is bounded by matcher.maxRefObjects below;
#     NOT via referenceSelector.magLimit — a MagnitudeLimit needs a per-band fluxField and
#     the multi-band refcat has no literal `flux` field, which raises
#     KeyError: 'Could not find field flux in catalog'. Density cap lives in the matcher.) ---
config.astrometry_ref_loader.pixelMargin = 300

# --- MATCHER ---
# Two independent concerns, tuned separately (the key Cycle-2 lesson):
#   (1) SPEED: the O(N^2) asterism blowup is driven by the *count* of objects, so cap
#       numBrightStars + maxRefObjects. These break the 28-min hang -> ~8-min night.
#   (2) PRECISION: the *acceptance tolerances* must stay STRICT (near stack defaults),
#       else the matcher locks onto ~10" false-match solutions on the crowded field.
#       An earlier over-loosened pass (offset 900, minFrac 0.05, minPairs 15) accepted
#       ~10" fits on 87% of visits. Restored to strict defaults here.
m = config.astrometry.matcher
m.numBrightStars = 150        # (speed) patterns from the 150 brightest only
m.maxRefObjects = 3000        # (speed) bound the reference set on the dense field
m.maxOffsetPix = 400          # (precision) 180-deg handled in profile; residual pointing is small
m.maxRotationDeg = 1.0        # equatorial mount, no field rotation
m.minMatchedPairs = 30        # (precision) stack default — demand a well-supported solution
m.minFracMatchedPairs = 0.3   # (precision) stack default — reject loose/partial matches
m.minMatchDistPixels = 1.0    # (precision) tight final match tolerance
m.numPatternConsensus = 3
m.numPointsForShape = 6

# --- astrometry WCS fit ---
config.astrometry.maxMeanDistanceArcsec = 0.5   # the Cycle-2 precision gate
config.astrometry.matchDistanceSigma = 2.0      # clip spatial match outliers (stack default)
config.astrometry.doMagnitudeOutlierRejection = True
