# Map Nickel physical_filter (or band) -> reference-catalog band code (PS1_DR2)
for source, target in [
    ("B", "g"),
    ("V", "g"),
    ("R", "r"),
    ("I", "i"),
    ("u", "g"),
    ("clear", "r"),
]:
    config.filterMap[source] = target
