# ruff: noqa: F821
# FGCM LUT configuration for Nickel BVRI
#
# Generates fgcmLookUpTable for Nickel filters using the standard FGCM
# atmosphere table.

# Filters to include in the LUT
config.physicalFilters = ["b", "v", "r", "i"]

# Atmosphere table to use (from fgcm)
config.atmosphereTableName = "fgcm_atm_lsst2"

# Optional: adjust SED/throughput tables here if needed
