# CTIO 1.0m / Y4KCam, 2x2 binned

The binned-readout variant of `instruments/ctio1m/`. See `profile.py` for why
it is a separate instrument. `camera/` and `configs/` are symlinks to the base.

Use it by pointing a config at this directory:

    INSTRUMENT_DIR: /path/to/stips/instruments/ctio1m_bin2

Example: `scripts/config/ctio1m/pipeline_bin2_e2.yaml`.
