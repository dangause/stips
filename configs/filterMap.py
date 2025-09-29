# Map Nickel physical_filter (or band) -> reference-catalog band code (PS1_DR2)
for source, target in [
    ("B", "monster_ComCam_g"),
    ("V", "monster_ComCam_g"),
    ("R", "monster_ComCam_r"),
    ("I", "monster_ComCam_i"),
]:
    config.filterMap[source] = target
