# Reference band -> refcat-column filter map (framework default).
#
# Maps each instrument physical_filter (upper-case) and band (lower-case) to the
# reference-catalog flux column it is calibrated against. The column choices here
# (band -> nearest MONSTER ComCam band) are a REFERENCE tuning derived from the
# Nickel 1-m's Johnson-Cousins set against the MONSTER refcat; the *right* mapping
# depends on both the instrument's filter inventory and the refcat in use, so a
# fork with different filters or a different refcat should drop its own
# ``filter_map.py`` into ``instruments/<name>/configs/`` (resolved
# instrument-dir-first). Analysis tasks KeyError on a physical_filter that is
# absent from this map, so every filter an instrument can produce must appear as
# BOTH its lower-case band and its upper-case physical_filter key.
#
# Instruments covered by this reference map:
#   - Nickel 1-m: B/V/R/I (+ clear, Sloan gp/rp, narrowband Halpha/OIII)
#   - CTIO 1.0m / Y4KCam: U/B/V/R/I
for source, target in [
    # Lower-case (band dimension)
    ("b", "monster_ComCam_g"),
    ("v", "monster_ComCam_g"),
    ("r", "monster_ComCam_r"),
    ("i", "monster_ComCam_i"),
    ("u", "monster_ComCam_g"),
    ("clear", "monster_ComCam_r"),
    # Upper-case (physical_filter dimension)
    ("U", "monster_ComCam_g"),
    ("B", "monster_ComCam_g"),
    ("V", "monster_ComCam_g"),
    ("R", "monster_ComCam_r"),
    ("I", "monster_ComCam_i"),
    ("CLEAR", "monster_ComCam_r"),
    # Sloan filters (closest MONSTER band)
    ("gp", "monster_ComCam_g"),
    ("rp", "monster_ComCam_r"),
    # Narrowband (approximate broadband mapping for astrometry refcat)
    ("halpha", "monster_ComCam_r"),
    ("Halpha", "monster_ComCam_r"),
    ("oiii", "monster_ComCam_g"),
    ("OIII", "monster_ComCam_g"),
]:
    config.filterMap[source] = target
# ruff: noqa: F821
