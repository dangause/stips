# ruff: noqa: F821
# CTIO 1.0m / Y4KCam (2x2 binned) -- sparse-field calibrateImage config.
#
# For short exposures of bright targets (the 2009 WASP-18 TraMoS nights are
# 1 s frames with ~15 Gaia DR3 stars per 20' field). The framework default
# (DRP.yaml: astrometry.maxIter=12, maxMeanDistanceArcsec=60) re-runs the
# matcher twelve times and keeps the LAST iteration; on these frames the fit
# converges to ~0.3" by iteration 2-3 and then, because the stop criterion
# (minMatchDistanceArcSec=0.001") is never met, a later iteration drifts onto
# a 10-25" false solution with more (spurious) matches, which the 60" gate
# accepts. Photometric matching then finds nothing and the frame is lost
# ("MatcherFailure: No matches to use for photocal") -- 37% of 2009-10-28.
#
# Measured on 24 such frames (cluster job 90975, 2026-11-07): maxIter=3 alone
# recovers 16 of 18 run (final fits 0.3-0.4" on 12-16 matches), whereas a
# tighter search window (matcher.maxOffsetPix=60) or minMatchDistanceArcSec=0.5
# recover 1-5 of 24. Everything else is the neutral default (loaded first so
# the stage-1 measurement schema is complete).
import os

config.load(
    os.path.join(
        os.environ["STIPS_DEFAULTS"], "configs", "calibrateImage", "neutral_default.py"
    )
)
config.astrometry.maxIter = 3
