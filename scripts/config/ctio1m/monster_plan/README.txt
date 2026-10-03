# MONSTER refcat shard plans for CTIO1m validation fields.
#
# Each new field needs its the_monster shards dumped from the Rubin Science
# Platform (dp1 Butler) with refcats/scripts/dump_monster_shards.py, then placed
# in $REFCAT_REPO/data/refcats/the_monster_20250219_afw/ (where bootstrap globs
# refcat_htm7_*.fits) and re-bootstrapped.
#
# PG1047+003 field (RA 162.54, Dec -0.022), 0.45deg cone -> 6 HTM7 shards
#   for the CTIO 2007-03-21 V test. See missing_htm7_ids.txt.
#
# SA98 Landolt field (RA 102.9863, Dec -0.3719), 0.6deg cone -> 25 HTM7 shards
#   for the coadd + PS1 DIA validation (pipeline_coadd_dia.yaml / pipeline_ps1_dia.yaml).
#   See sa98_cones.csv (authoritative input for the dump tool) and sa98_htm7_ids.txt.
#   On RSP:  python dump_monster_shards.py --cones-file sa98_cones.csv
