# Nickel color terms — recipe

The color-term fitting **tool** is now framework code:
`stips-colorterms-fit` (`stips.pipeline_tools.fit_colorterms`). It is
instrument-neutral and parameterized by the active instrument profile. This
directory keeps only the Nickel-specific **recipe** — the exact invocation and
inputs that produced the curated color-term config — plus one Nickel-only input
generator (the synthetic-photometry fitter, below).

The fitted **output** lives at `instruments/nickel/configs/colorterms.py`
(the per-instrument file of the tiering contract; see
`packages/obs_stips/instrument_defaults/README.md`), **not** here.

## What the tool does

For each band it least-squares fits
`m_Nickel = m_primary + c0 + c1·(primary − secondary) [+ c2·(…)²]`
against matched standard-star photometry, then emits a drop-in
`ColortermDict` config. `c0` is absorbed by `calibrateImage`'s per-visit
photometric zeropoint; `c1` (the color slope) removes color-dependent
systematics. See the module docstring for the full algorithm.

## Nickel recipe — the live `ps1*` block (Landolt fit)

The authoritative Nickel color terms are the PS1→BVRI terms in
`configs/colorterms.py`, empirically fit against Landolt standard stars. To
regenerate them (run inside the LSST stack env so `astroquery`/`stips_refcats`
are importable, with `INSTRUMENT_DIR` pointing at `instruments/nickel`):

```bash
stips-colorterms-fit \
  --landolt-catalog scripts/config/landolt_validation/landolt_catalog.csv \
  --ref-catalog ps1 \
  --bands B V R I \
  --out instruments/nickel/configs/colorterms.py
```

`--landolt-catalog` matches each Landolt standard to PS1 DR2 mean PSF g/r/i
(5″ cone) before fitting. The default per-band color definitions reproduce the Nickel
choices (B/V use g−r, R/I use r−i). `SA 109-199` is excluded by default
(`--exclude`).

If you already have a matched table (reference mags + one column per band),
skip the query:

```bash
stips-colorterms-fit --matched matched_photometry.csv \
  --ref-catalog ps1 --out instruments/nickel/configs/colorterms.py
```

Review the printed coefficients and residual RMS, then commit the file.

## Nickel-only input: the synthetic `*monster*` fitter

`nickel_colorterm_fitter.py` is a **Nickel-specific** synthetic-photometry
engine (it integrates FGCM stellar templates through the Nickel SVO filter
curves `LICK/LICK.{B,V,R,I}` and MONSTER/ComCam throughputs). It is genuinely
instrument-specific and is **not** part of the framework tool; it is kept here
as the input generator for the MONSTER color-term block. It emits per-band
spline YAMLs, which the framework tool converts into the config format:

```bash
# 1) generate per-band spline YAMLs (needs fgcm + MONSTER throughputs)
python instruments/nickel/colorterms/nickel_colorterm_fitter.py \
  --monster-throughput-dir /path/to/the_monster/data/throughputs \
  --output-dir ./nickel_colorterms_output --bands B V R I

# 2) convert the splines into a ColortermDict config (framework tool)
stips-colorterms-fit --from-spline-dir ./nickel_colorterms_output \
  --ref-catalog monster --out monster_colorterms.py
```

Merge the `*monster*` block into `configs/colorterms.py` as needed.

## Producing color terms for a NEW instrument

The framework tool is reused unchanged — only the fitted output and this recipe
are per-instrument:

1. Match standard-star reference magnitudes (PS1/Gaia/…) to your instrument's
   calibrated magnitudes; write them to a table (one column per reference mag,
   one per instrument band).
2. Run `stips-colorterms-fit --matched <table> --ref-catalog <ps1|gaia|monster>
   --out instruments/<name>/configs/colorterms.py`, adding
   `--color BAND:PRIMARY:SECONDARY` if your band→color mapping differs from the
   Nickel default.
3. Review the coefficients + residual RMS, commit the file, and record your
   exact invocation here in `instruments/<name>/colorterms/README.md`.
