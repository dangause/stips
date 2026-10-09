# Reference catalogs

`calibrateImage` fits each exposure's astrometric solution and photometric
zero point by matching its stars to a reference catalog. STIPS can use two
sources, chosen with the `refcat:` section of the config.

| `refcat.mode` | Catalogs | How they arrive |
|---|---|---|
| `monster` (default) | Rubin's MONSTER, an all-sky catalog merged from Gaia, Pan-STARRS, and other surveys | Shards you download once and keep under `REFCAT_REPO` |
| `gaia_ps1` | Gaia DR3 for astrometry, Pan-STARRS1 DR2 for photometry | Fetched automatically for each target before science |
| `gaia` | Gaia DR3 only | Fetched automatically; for fields south of −30°, outside Pan-STARRS |

```yaml
refcat:
  mode: gaia_ps1
  radius_deg: 0.3      # cone fetched around ra/dec; cover your dithers
```

Not every band can be calibrated in every mode. A band needs a reference
filter, and with colour terms it needs a term for that catalog too. Bands
that have neither fail calibration. As configured today:

| Instrument | `monster` | `gaia_ps1` | `gaia` |
|---|---|---|---|
| Nickel | B, V, R, I, g′, r′, Hα, [OIII] | B, V, R, I, r′, i′ | None yet: its Gaia colour terms name columns the catalog lacks |
| CTIO | B, V, R, I | R, I | B, V, R, I |

MONSTER cannot calibrate Nickel i′, and no mode calibrates CTIO U. For
Nickel, `gaia_ps1` is the mode checked against Landolt standards; see
{doc}`instruments/nickel/photometry`. On-demand fetching covers one cone
around `ra`/`dec`. For a config spanning several fields, fetch each field
first with `stips refcat fetch`.

## MONSTER shards

Setting up a repository (`stips bootstrap`, or the first step of `stips run`)
currently ingests MONSTER shards whatever the mode, so every repository needs
them. They are FITS files, one per HTM level-7 sky cell, stored in

```text
$REFCAT_REPO/data/refcats/the_monster_20250219_afw/refcat_htm7_<id>.fits
```

They must cover every pointing you process; a gap shows up as
`Not enough datasets (0) found` when the quantum graph is built. The shards
come from Rubin's Data Preview 1 on the [Rubin Science
Platform](https://data.lsst.cloud/), which needs an RSP account:

1. List the sky cells your fields need. This step uses the Rubin stack, so
   run it through `make`, which activates the stack:

   ```bash
   STACK_DIR=/path/to/lsst_stack make refcat-cones \
       ARGS="--ras 210.910750 --decs 54.311694 --radius-arcmin 6 --outdir $REFCAT_REPO/data/monster_plan"
   ```

   This writes `htm7_list.txt` to `$REFCAT_REPO/data/monster_plan/`, where
   step 3 looks for it. `--fits-dir` reads pointings from raw FITS files
   instead, and `--scan-configs` from STIPS configs.

2. On the RSP, upload `htm7_list.txt` and
   `packages/refcats/scripts/dump_monster_shards.py`, then run

   ```bash
   python dump_monster_shards.py --htm7-file htm7_list.txt
   ```

   and download the tarball it writes, `the_monster_20250219_new.tgz`.

3. Merge the shards into your catalog directory, then compare them with the
   list from step 1:

   ```bash
   SHARDS=$REFCAT_REPO/data/refcats/the_monster_20250219_afw
   stips-refcats merge the_monster_20250219_new.tgz --shard-dir $SHARDS
   stips-refcats status --shard-dir $SHARDS
   ```

Do this before creating the repository: bootstrap ingests the shard directory
once, when it sets the repository up, and does not pick up shards added later.

## On-demand Gaia and Pan-STARRS

With `mode: gaia_ps1` or `mode: gaia`, `stips run` checks the repository's
coverage of a cone around `ra`/`dec` before science, and fetches, converts,
and ingests only what is missing. This needs network access to the Gaia
archive and MAST. If the fetch fails, the run stops with the cause instead of
failing every night later.

To check or fetch a cone by hand, for example before running steps
individually:

```bash
stips -c target.yaml refcat status --ra 210.910750 --dec 54.311694   # ingested sky cells
stips -c target.yaml refcat fetch --ra 210.910750 --dec 54.311694 --radius 0.3
```

Pan-STARRS covers declinations above about −30°. Further south, use
`mode: gaia`, which calibrates photometry against Gaia, or MONSTER.
