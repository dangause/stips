# Nickel calibrateImage tuning — recipe

The calibrateImage tuning **harness** is now framework code:
`stips-tune-calibrate-image` (`stips.pipeline_tools.tune_calibrate_image`). It is
instrument-neutral and parameterized by the active instrument profile. This
directory keeps only the Nickel-specific **recipe** — the exact invocation and
the Nickel search space (`tune.yaml`) that produced the curated tuned configs.

The tuned **outputs** (the winning `calibrateImage` overrides) live under
`instruments/nickel/configs/calibrateImage/tuned_configs/` (`dense_strict.py`,
`2023ixf_relaxed.py`, `best_calib_t071.py`, …), **not** here.

## What the tool does

An Optuna search samples `calibrateImage` config parameters from `tune.yaml`,
runs `pipetask run` on each science visit, reads `visitSummary` metric medians,
combines them into a single score (min-direction `weight·value/target`,
max-direction `weight·target/value`) with a failure penalty, and records every
trial. See the module docstring for the full algorithm.

`tune.yaml` (kept here) is the Nickel-specific input: the parameter search space
(PSF detection/selection, astrometry matcher, aperture-correction and
calibration-flux S/N knobs), the metric targets (`psfSigma`, `astromOffset*`,
`skyNoise`, `magLim`), and the static `overrides_prelude` injected into every
trial.

## Nickel recipe

Process a set of Nickel science visits first (`stips science`), so postISR +
calib inputs exist. Then run the tuner inside the LSST stack env (with
`INSTRUMENT_DIR` pointing at `instruments/nickel`):

```bash
stips-tune-calibrate-image \
  --repo "$REPO" \
  --pipeline-dir <dir containing pipelines/ProcessCcd.yaml> \
  --workdir ./tuning_out \
  --config instruments/nickel/tuning/tune.yaml \
  --trials 60 \
  --jobs 6
```

The instrument name (`Nickel`) and collection prefix used for default
input/output collections come from the active profile; override with
`--instrument` / `--collection-prefix`. postISR and calib-chain collections are
auto-discovered (`--inputs-postisr` / `--calib-chain` to override). Each trial's
overrides file is written under `./tuning_out/trials/tNNN/`; the best trial is
printed as JSON at the end.

Copy the winning overrides file to
`instruments/nickel/configs/calibrateImage/tuned_configs/<name>.py`, prune the
auto-generated header, and commit it (e.g. `best_calib_t071.py` was trial 71).

## Producing tuned configs for a NEW instrument

The tool is reused unchanged — only `tune.yaml`, the tuned outputs, and this
recipe are per-instrument:

1. Process science visits for your instrument (`stips science`).
2. Write a `tune.yaml` for your camera's `calibrateImage` knobs and metric
   targets (start from this one).
3. Run `stips-tune-calibrate-image --repo $REPO --pipeline-dir <dir> --workdir
   <out> --config tune.yaml --trials N`.
4. Commit the best trial's overrides under
   `instruments/<name>/configs/calibrateImage/tuned_configs/` and record the
   invocation in `instruments/<name>/tuning/README.md`.
