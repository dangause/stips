# Troubleshooting

Start with `logs/<run id>/summary.txt`, then the failing step's log; see
{doc}`logging`. For problems with the Rubin stack itself, the [Rubin
Community Forum](https://community.lsst.org/) is the place to ask.

## Installation and setup

**`No loadLSST script found in ...`**
: `STACK_DIR` must be the directory that contains `loadLSST.sh`, where you
  ran `lsstinstall`. See {doc}`install-rubin-stack`.

**`stips: command not found`**
: Activate the environment with `source .venv/bin/activate`, or prefix
  commands with `uv run`.

**`ModuleNotFoundError` after moving the checkout**
: The `.venv` records absolute paths. Rebuild it: `rm -rf .venv && uv sync`.

**`No module named 'tenacity'` from `stips download`**
: The vendored Lick archive client needs it: `uv pip install tenacity`.

**`No config provided`**
: Every command needs `-c <config.yaml>` before the command name:
  `stips -c target.yaml calibs 20230519`.

**`INSTRUMENT_PACKAGE is removed`**
: An old config sets `INSTRUMENT_PACKAGE`. Replace it with `INSTRUMENT_DIR`,
  the directory containing your instrument's `profile.py`.

**`CP_PIPE_DIR does not exist`**
: Remove `CP_PIPE_DIR` from the config so STIPS finds `cp_pipe` in the stack,
  or set it to the right path.

## Bootstrap

**`No MONSTER refcat shards found under ...`**
: Bootstrap needs MONSTER shards in
  `REFCAT_REPO/data/refcats/the_monster_20250219_afw/`. See
  {doc}`reference-catalogs`.

**`Bootstrap script not found`**
: Run `stips` from the STIPS checkout, or keep your instrument directory at
  `instruments/<name>/` inside it.

**Database or locking errors**
: The repository's filesystem must support `flock`; some network filesystems
  are mounted without it. Put the repository on a local disk to check.

## Calibration and science

**Raw data not found**
: Frames must be in `RAW_PARENT_DIR/<night>/raw/`. Download them with
  `stips download <night>`.

**No science frames for the object**
: `object` must appear in the frames' `OBJECT` header. Check one with
  `python -c "from astropy.io import fits; print(fits.getheader('frame.fits')['OBJECT'])"`.

**`FileNotFoundError: astrometry_ref_cat` or `Not enough datasets (0) found`**
: Either an exposure's header coordinates are wrong, or the reference
  catalogs do not cover it. Nickel's `DEC` keyword can freeze at an earlier
  pointing; `stips run` drops such exposures by comparing each pointing with
  the target, and standalone `stips science` does so when given `--ra` and
  `--dec`. Otherwise extend the MONSTER shards or the `gaia_ps1` cone; see
  {doc}`reference-catalogs`.

**`stips run` stops with a reference-catalog error before science**
: The on-demand Gaia or Pan-STARRS fetch failed, usually for lack of network
  access. Fix the cause, or use `refcat.mode: monster`.

**Science fails for a southern field in `gaia_ps1` mode**
: Pan-STARRS does not reach below −30°. The fetch skips it without stopping
  the run, and photometric calibration then has no reference stars. Use
  `refcat.mode: gaia`.

**Some exposures fail calibration**
: Star-poor fields can defeat the primary `calibrateImage` config. Keep
  `use_fallbacks` on and list fallback configs; see
  {doc}`instruments/nickel/science-configs`.
  `REPO/processing_log/` shows which configs each night needed.

## Difference imaging

**DIA reports failure but produced no difference images**
: The template does not overlap the science pointings. Increase
  `template.size` so it covers the field plus your dithers.

**`NoKernelCandidatesError`**
: Too few stars are shared by template and science image to match their
  PSFs, usually for the same coverage reason.

**Bright stars leave positive residuals with PS1 templates**
: The template was not decoded from PS1's compressed pixel format. Ingested
  templates record `TEMPLATE_ASINH_DECODED` in their metadata; re-ingest with
  `stips ps1-template ... --overwrite` and rerun DIA.

**Negative or low supernova flux with a coadd template**
: A template night still contained the supernova. Rebuild the coadd from
  nights without it.

## Forced photometry

**Negative flux at every epoch**
: The coordinates are probably rounded. Use six or more decimal places; see
  {doc}`new-campaign`.

**No forced photometry for a night**
: Forced photometry runs only where difference imaging succeeded. Check that
  night's `dia/` log.
