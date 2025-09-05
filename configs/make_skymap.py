# Discrete SkyMap config generated for Nickel
# Coadd/Skymap identifier used by butler: "nickel_discrete"

config.name = "nickel_discrete"           # coadd/skymap name used by pipelines
config.skyMap.name = "discrete"           # choose the SkyMap type

# All discrete-specific settings live under ["discrete"]
d = config.skyMap["discrete"]

# Tract geometry (from your script output)
d.raList     = [251.904217]   # degrees
d.decList    = [  2.255570]   # degrees
d.radiusList = [ 18.961026]   # degrees  (bounding circle radius)

# General geometry (leave defaults if unsure)
d.pixelScale    = 0.421529    # arcsec/pixel (Nickel)
d.tractOverlap  = 0.0         # degrees (overlap between tracts)
# Optional (defaults are fine for small images):
# d.patchInnerDimensions = [4000, 4000]
# d.patchBorder          = [100, 100]
