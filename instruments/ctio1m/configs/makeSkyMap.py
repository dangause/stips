# Rings SkyMap for CTIO 1.0m / Y4KCam.
#
# Resolved instrument-dir-first by core/stack.py -> SKYMAP_CFG (shadows the
# framework reference $STIPS_DEFAULTS/configs/makeSkyMap.py). The geometry uses
# Y4KCam's native plate scale, which also gives a distinct SkyMap hash from the
# Nickel reference so each registers cleanly under its own name.

config.name = "ctio1mRings-v1"  # the SkyMap (matches profile.skymap_name)
config.skyMap.name = "rings"

rings = config.skyMap["rings"]
rings.numRings = 40  # number of declination rings (controls # of tracts)
rings.projection = "TAN"
rings.tractOverlap = 1.0 / 60  # 1 arcmin tract overlap
rings.pixelScale = 0.289  # arcsec/pixel (Y4KCam native: 0.289"/15um px)
rings.patchInnerDimensions = [4000, 4000]
rings.patchBorder = 100
# ruff: noqa: F821
