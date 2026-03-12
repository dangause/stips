# Minimal rings SkyMap for Nickel

config.name = "nickelRings-v1"  # the SkyMap
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
