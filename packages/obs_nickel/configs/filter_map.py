# Map Nickel physical filters to reference-catalog filter names.
# Include both lowercase (band dimension) and uppercase (physical_filter
# dimension) keys so analysis tasks don't KeyError on 'R', 'B', etc.
# Map Nickel filters to MONSTER refcat column names.
# Use MONSTER column names (monster_ComCam_*) for both band and physical_filter keys
# so refcat loads do not look for plain g_flux/r_flux fields.
for source, target in [
    # Lower-case (band dimension)
    ("b", "monster_ComCam_g"),
    ("v", "monster_ComCam_g"),
    ("r", "monster_ComCam_r"),
    ("i", "monster_ComCam_i"),
    ("u", "monster_ComCam_g"),
    ("clear", "monster_ComCam_r"),
    # Upper-case (physical_filter dimension)
    ("B", "monster_ComCam_g"),
    ("V", "monster_ComCam_g"),
    ("R", "monster_ComCam_r"),
    ("I", "monster_ComCam_i"),
    ("CLEAR", "monster_ComCam_r"),
]:
    config.filterMap[source] = target
# ruff: noqa: F821
