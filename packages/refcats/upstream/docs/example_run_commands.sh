python scripts/gaia_fetch.py \
  --butler /Users/dangause/Developer/lick/lsst/data/nickel/repo \
  --instrument Nickel \
  --registry-where "visit.observation_reason='science'" \
  --radius-deg 0.09 \
  --batch-size 200 \
  --outdir ./data/gaia_dr3_cones_batched \
  --merged-parquet ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.parquet \
  --merged-csv ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv


# gaia dr3 from butler repo
python scripts/gaia_fetch.py \
  --butler /Users/dangause/Developer/lick/lsst/data/nickel/repo \
  --instrument Nickel \
  --registry-where "visit.observation_reason='science'" \
  --radius-deg 0.09 \
  --batch-size 200 \
  --outdir ./data/gaia_dr3_cones_batched \
  --merged-parquet ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.parquet \
  --merged-csv ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv \
  --overwrite


# gaia dr3 from fits directory
python scripts/gaia_fetch.py \
  --fits-dir "/Users/dangause/Developer/lick/data" \
  --fits-recursive \
  --radius-deg 0.09 \
  --batch-size 200 \
  --g-min 9 --g-max 19.5 \
  --outdir ./data/gaia_dr3_cones_batched \
  --merged-parquet ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.parquet \
  --merged-csv ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv \
  --overwrite




  python scripts/ps1_fetch_mast.py \
  --butler /Users/dangause/Developer/lick/lsst/data/nickel/repo \
  --instrument Nickel \
  --registry-where "visit.observation_reason='science'" \
  --radius-arcmin 5.4 \
  --mag-band r --mag-min 12 --mag-max 20.5 \
  --batch-size 50 \
  --outdir ./data/ps1_cones_batched \
  --merged-parquet ./data/ps1_all_cones/merged_ps1_cones.parquet \
  --merged-csv ./data/ps1_all_cones/merged_ps1_cones.csv


# ps1 from fits directory
python scripts/ps1_fetch_mast.py \
  --fits-dir "/Users/dangause/Developer/lick/data" \
  --fits-recursive \
  --radius-arcmin 5.4 \
  --mag-band r --mag-min 12 --mag-max 20.5 \
  --batch-size 51 \
  --outdir ./data/ps1_cones_batched \
  --merged-parquet ./data/ps1_all_cones/merged_ps1_cones.parquet \
  --merged-csv ./data/ps1_all_cones/merged_ps1_cones.csv \
  --overwrite
# (Optional) add --debug-fits to print a summary if any headers fail



# And for the monster refcat:
nickel-refcats cones \                                                      lsst-scipipe-10.1.0 09:08:03
  --fits-dir "$HOME/Developer/lick/data" \
  --fits-recursive \
  --radius-arcmin 6 \
  --depth 7 \
  --outdir ./data/monster_plan
