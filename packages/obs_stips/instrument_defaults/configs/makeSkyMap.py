# Minimal rings SkyMap -- FRAMEWORK DEFAULT (reference geometry from the Nickel 1-m).
#
# Resolved instrument-dir-first: bootstrap overrides the NAME via
# `-c name=$SKYMAP_NAME`, but the GEOMETRY below (pixelScale, ring count) is
# inherited silently unless a fork ships its own configs/makeSkyMap.py.
# instruments/ctio1m/configs/makeSkyMap.py is an example override (0.289"/px).
# A fork whose plate scale differs materially should override this file so its
# SkyMap hash and tract layout match its data. See instrument_defaults/README.md.

config.name = "nickelRings-v1"  # the SkyMap (bootstrap overrides via -c name=...)
config.skyMap.name = "rings"

rings = config.skyMap["rings"]
rings.numRings = 40  # number of declination rings (controls # of tracts)
rings.projection = "TAN"
rings.tractOverlap = 1.0 / 60  # 1 arcmin tract overlap
rings.pixelScale = (
    0.40  # arcsec/pixel (close to Nickel; exact value not critical for analysis)
)
rings.patchInnerDimensions = [4000, 4000]
rings.patchBorder = 100
# ruff: noqa: F821
