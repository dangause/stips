# Rings SkyMap for CTIO 0.9m telescope

config.name = "ctio0m9Rings-v1"
config.skyMap.name = "rings"

rings = config.skyMap["rings"]
rings.numRings = 40  # number of declination rings
rings.projection = "TAN"
rings.tractOverlap = 1.0 / 60  # 1 arcmin tract overlap
rings.pixelScale = 0.40  # arcsec/pixel (CTIO 0.9m ~0.4"/pix)
rings.patchInnerDimensions = [4000, 4000]
rings.patchBorder = 100
# ruff: noqa: F821
