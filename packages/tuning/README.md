# obs-nickel-tuning

**Calibration parameter optimization tools for the Nickel telescope.**

This package contains tools for automatically tuning LSST pipeline configuration parameters
to optimize performance for Nickel telescope data.

## Contents

- `calibrate_pipe_tuner/` - Automated tuning framework for CalibrateImage task
- `tune.yaml` - Tuning parameter space definitions
- `tune_calibrate_7.py` - Example tuning script
- `run_calibrate_tuner.py` - Runner script

## Usage

These tools are used during pipeline development to optimize configuration parameters
found in `packages/obs_nickel/configs/calibrateImage/tuned_configs/`.

**Note**: This package is NOT required for running the standard Nickel pipelines.
It's only needed if you're re-tuning the calibration parameters.

## Installation

```bash
pip install -e packages/tuning
```

## LSST Separation

This package is intentionally separated from the core `obs-nickel` package because:
- Tuning tools are development utilities, not runtime requirements
- They should not be included in LSST upstream submissions
- The tuned *results* (config files) live in `obs-nickel/configs/`, not the tuning tools themselves
