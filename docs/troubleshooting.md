# Troubleshooting

Start with the logs: every run writes `logs/{RUN_ID}/`, with one subdirectory
per step, a `pipeline.log`, and a `summary.txt` of success and failure counts.
See [Logging](logging.md).

## Setup

### `CP_PIPE_DIR` not found

STIPS asks the stack's EUPS for `cp_pipe` when `CP_PIPE_DIR` is unset. If that
fails, the stack may not be installed at `STACK_DIR`; set `CP_PIPE_DIR`
explicitly in the `env:` block.

### Raw data not found

`RAW_PARENT_DIR/{night}/raw/` must exist and hold FITS files. Fetch them with
`stips download <night>` (Nickel → Lick archive; CTIO → NOIRLab).

### `INSTRUMENT_PACKAGE is removed`

A stale config still sets `INSTRUMENT_PACKAGE` in `env:`. Replace it with
`INSTRUMENT_DIR: /path/to/instruments/<name>` — the directory containing
`profile.py`. `OBS_NICKEL` and `-p/--profile` no longer exist either.

## Science processing

### `FileNotFoundError: astrometry_ref_cat` (stale DEC headers)

The Nickel `DEC` keyword can freeze at a previous pointing. When `CRVAL2` and
`DEC` agree on the wrong value, the translator's fallback cannot catch it.
Pre-flight coordinate validation compares each exposure's coordinates with the
target's (5° tolerance) and drops the bad ones. It runs automatically under
`stips run`; for standalone `stips science`, pass `--ra` and `--dec`.

### `MissingDatasetTypeError` for `astrometry_ref_cat` or `panstarrs1_dr2`

Reference catalogs are missing. In `gaia_ps1` mode, `stips run` aborts early
when the on-demand refcat fetch fails (no network, missing `astroquery`) and
reports the cause. Fix it, or use `refcat.mode: monster` if the repo already
holds refcats.

### Southern fields have no PS1 coverage

Pan-STARRS1 covers Dec ≳ −30° only. Astrometry against Gaia DR3 still works,
but photometric calibration needs `refcat.mode: gaia` or MONSTER shards
(`refcat.mode: monster`). For templates, see
[the next section](#templates-and-difference-imaging).

## Templates and difference imaging

### DIA reports failure but the pipeline exited 0

STIPS counts the difference images after `pipetask` finishes. Zero images
usually means `rewarpTemplate` found no template overlap — the most common DIA
failure. Check the template's footprint against the science pointings.

### PS1 template overlap failures or `NoKernelCandidatesError`

The PS1 cutout defaults to 0.2° (`--size`, or `template.size` in YAML). Size it
to comfortably exceed the camera's field of view plus the dither range: Nickel
is ~6.3′, but CTIO Y4KCam is ~20′, where the default leaves dithered pointings
with no PSF-matching kernel candidates. The 2023ixf configs use 0.4°. A larger
size triggers a re-download.

### Bright stars leave positive residuals

PS1 stores stack pixels asinh-compressed (`BSOFTEN`/`BOFFSET` header keys).
STIPS decodes them during ingest; if that step is skipped, faint stars subtract
cleanly but bright ones leave large positive residuals and kernel candidates
run short. This is not saturation. Check for `TEMPLATE_ASINH_DECODED` in the
ingested template's metadata.

### Unstable kernels with PS1 templates

PS1 templates must be calibrated to nJy at ingest. Left in raw ADU, the DIA
kernel must absorb a ~363× flux ratio on top of PSF matching. After
re-ingesting templates, rerun any existing DIA.

### Negative or underestimated difference flux with coadd templates

A coadd built from nights when the supernova was still bright bakes its flux
into the template. Build coadds only from SN-free nights, or use PS1 templates
for early epochs.

### Southern templates

1. **`template.type: coadd`** — a same-instrument coadd from SN-free nights.
   This is the validated path.
2. **`template.type: skymapper`** — a SkyMapper DR4 cutout, for when no
   SN-free nights exist. Cutouts are capped at 0.17°, frames are single-epoch,
   and only `r` and `i` are mapped (SkyMapper `v` is a violet filter, not
   Johnson V). Always pass `--subtract-config dia/subtractImages_skymapper.py`
   (or `configs.dia.subtract_images`). See
   [SkyMapper templates](skymapper-template-validation.md) for measured
   performance.

## Forced photometry

### Forced-photometry flux is negative at every epoch

The coordinates are probably rounded. Use full TNS precision — see
[Configuration](configuration.md#the-pipeline-sections). On Nickel's
0.37″/pixel scale, rounding to 2 decimal places misses the source and measures
the host galaxy's background instead.

## Fallback configs

Each fallback `calibrateImage` config writes to its own RUN collection
(`/run_fb1`, `/run_fb2`, ...) under the same CHAINED parent as the primary
`/run`, because the Butler requires one config per task label in a RUN
collection. Downstream steps should read the CHAINED parent `processCcd/{ts}`,
never an individual `/run` or `/run_fb*`. See
[Science configs](science-configs.md).
