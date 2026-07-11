# Nickel defects — recipe

The defect-generation **tool** is now framework code:
`stips-defects-build` (`stips.pipeline_tools.build_defects`). It is
instrument-neutral and parameterized by the active instrument profile. This
directory keeps only the Nickel-specific **recipe** — the exact invocation and
thresholds that produced the curated defect products.

The generated products live under
`instruments/nickel/obs_nickel_data/Nickel/defects/ccd0/<calibdate>.ecsv`
(a real EUPS data package), not here.

## Algorithm

`stips-defects-build` builds a per-pixel median flat, auto-detects defect
rectangles (Gaussian smooth → ratio threshold outside `[ratio_lo, ratio_hi]` →
morphological opening → connected components ≥ `min_area`), optionally merges
manual rectangles, and emits a CSV and/or a curated ECSV file and/or ingests a
Butler `defects` calibration. See the module docstring for details.

## Nickel recipe

Nickel is a single-CCD camera (detector `0`, name `ccd0`). The current curated
map was produced with the tool's default thresholds:

| Parameter    | Value  | Flag          |
|--------------|--------|---------------|
| Gaussian σ   | 7 px   | `--sigma`     |
| Upper ratio  | 1.10   | `--ratio-hi`  |
| Lower ratio  | 0.90   | `--ratio-lo`  |
| Min area     | 8 px   | `--min-area`  |
| Open kernel  | 2      | `--open`      |

Regenerate (run inside the LSST stack env, with `INSTRUMENT_DIR` pointing at
`instruments/nickel`):

```bash
stips-defects-build \
  --repo   "$REPO" \
  --collection "<Nickel cpFlat run collection>" \
  --ecsv-out instruments/nickel/obs_nickel_data/Nickel/defects/ccd0/ \
  --calib-date 1970-01-01T00:00:00 \
  --plot
```

This writes `19700101T000000.ecsv` (all-time validity). Commit the file, then
ingest the curated calibrations:

```bash
butler write-curated-calibrations "$REPO" lsst.obs.stips.active.Instrument
```

To also register/certify a Butler `defects` calib directly (instead of the
curated-data-package route) add `--ingest --register --certify --begin <date>
--end <date>`.

## Producing a defect package for a NEW instrument

The tool is reused unchanged — only the products and this recipe are
per-instrument:

1. Build calibration flats for your instrument (`stips calibs`).
2. Run `stips-defects-build --repo $REPO --collection <cpFlat run>
   --ecsv-out instruments/<name>/obs_<name>_data/<Prefix>/defects/<det>/`,
   tuning `--sigma/--ratio-hi/--ratio-lo/--min-area/--open` for your sensor and
   adding `--manual-box X0 Y0 W H` for defects the auto-pass misses. Set
   `--detector`/`--detector-name`/`--raft-name` for multi-CCD or non-default
   detector naming.
3. Commit the emitted `.ecsv` under your curated data package and record your
   exact invocation + thresholds in `instruments/<name>/defects/README.md`.
