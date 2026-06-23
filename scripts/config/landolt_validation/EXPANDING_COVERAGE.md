# Expanding MONSTER Refcat Coverage for Landolt Validation

The local MONSTER refcat (`the_monster_20250219_local`) is a partial-sky
ingestion of shards previously needed by other Nickel campaigns. Three of the
four Landolt Tier 1 nights (20210208, 20240905, 20240906) fail at qgraph build
with:

    FileNotFoundError: Not enough datasets (0) found for non-optional
    connection calibrateImage.astrometry_ref_cat (the_monster_20250219_local)

because the visit footprints fall on HTM7 cells we don't have locally. This
runbook expands coverage so qgraph build succeeds for all Landolt fields.

## Tooling

All steps use existing tools — no Landolt-specific scripts:

- `scripts/utilities/recompute_missing_shards.py` — queries the Butler for
  visit centroids, computes the HTM7 shards needed at 6 arcmin (Nickel FOV),
  subtracts what's already on disk, writes `missing_htm7_ids.txt` +
  `htm7_list.txt` + `cones.csv` to a plan dir.
- `packages/refcats/scripts/dump_monster_shards.py` — runs on the Rubin
  Science Platform; dumps requested HTM7 shards from the dp1 Butler and
  tarballs them.
- `nickel-refcats merge` (from `packages/refcats`) — extracts the tarball
  into the local shard dir and invalidates the ECSV so bootstrap rebuilds it.
- `nickel-refcats status` — sanity-checks coverage at any point.

## Workflow

### 1. Compute what's missing (local)

Raws must already be ingested (the Landolt repo's calibs step does this).

```bash
source /Users/dangause/Developer/lick/lsst/lsst_stack/loadLSST.bash
setup lsst_distrib
setup -r packages/obs_nickel obs_nickel

python scripts/utilities/recompute_missing_shards.py \
  --repo /Users/dangause/Developer/lick/lsst/data/nickel/landolt_validation_repo \
  --shard-dir $REFCAT_REPO/data/refcats/the_monster_20250219_afw \
  --plan-dir scripts/config/landolt_validation/monster_plan
```

This writes:
- `monster_plan/missing_htm7_ids.txt` — IDs to upload to RSP
- `monster_plan/htm7_list.txt` — full needed list
- `monster_plan/cones.csv` — RA/Dec/radius per visit

### 2. Dump shards on RSP

On the RSP, clone the nickel_processing_suite repo (or just push the script +
ID file), then:

```bash
python packages/refcats/scripts/dump_monster_shards.py \
  --htm7-file scripts/config/landolt_validation/monster_plan/missing_htm7_ids.txt
```

Outputs `the_monster_20250219_new.tgz` in the current directory.

### 3. Merge locally

```bash
nickel-refcats merge the_monster_20250219_new.tgz \
  --shard-dir $REFCAT_REPO/data/refcats/the_monster_20250219_afw
```

This extracts the new shards alongside the existing ones and deletes the
stale `filename_to_htm.ecsv` so bootstrap rebuilds it.

### 4. Drop the existing refcat collection and re-bootstrap

`scripts/pipeline/00_bootstrap_repo.sh` skips `butler ingest-files` if the
`refcats/the_monster_20250219_local` collection already exists, so we must
drop it first:

```bash
REPO=/Users/dangause/Developer/lick/lsst/data/nickel/landolt_validation_repo
butler remove-collections $REPO refcats/the_monster_20250219_local --no-confirm
butler remove-collections $REPO refcats --no-confirm   # the chain
```

Then re-bootstrap (only the refcat ingestion step matters; calibs and
science collections are preserved):

```bash
nickel run scripts/config/landolt_validation/pipeline_landolt.yaml \
  --skip-calibs --skip-science    # bootstrap only; adjust flags if needed
```

If `--skip-*` flags don't bypass everything cleanly, just shell out:

```bash
bash scripts/pipeline/00_bootstrap_repo.sh
```

### 5. Verify coverage

```bash
nickel-refcats status --shard-dir $REFCAT_REPO/data/refcats/the_monster_20250219_afw
```

Compares `monster_plan/htm7_list.txt` to shards on disk and reports any
remaining gaps.

### 6. Re-run pipeline and validation

```bash
nickel run scripts/config/landolt_validation/pipeline_landolt.yaml

nickel landolt-validate scripts/config/landolt_validation/pipeline_landolt.yaml \
  --catalog scripts/config/landolt_validation/landolt_catalog.csv \
  -o analysis/landolt_validation.csv
```

Expected: 4 nights × 11 Landolt fields × 4 BVRI bands processed, covering
the full Landolt B-V color range (-0.19 to +1.74) for poster color-term
fits.

## Why the object filter fix matters

`packages/stips/src/stips/core/science.py` now special-
cases `object='landolt_validation'` and reads `landolt_catalog.csv` directly
to build an `exposure.target_name IN (...)` clause. Without this, the
pipeline would also process the non-Landolt science targets observed those
nights (SN 2020sgf, T_CrB, NGC_7469, …), each of which would need *its* own
HTM7 shards — far more than just expanding to cover Landolt fields.

The `recompute_missing_shards.py` script in step 1 queries *all* science
visits in the repo, so it will include shards for non-Landolt targets too.
That's harmless (extras don't break anything; downstream Nickel campaigns
benefit) but explains why the missing-shard count will exceed what's
strictly needed for Landolt-only processing.
