# Crosstalk for multi-amplifier instruments

Multi-amplifier detectors exhibit **crosstalk**: bright signal read out through
one amplifier induces a faint, scaled copy of itself in the others. The LSST
stack corrects this during ISR using a `CrosstalkCalib` — an N×N coefficient
matrix (N = number of amplifiers). STIPS lets any instrument declare or measure
that matrix and applies it automatically.

This applies only to multi-amp cameras (e.g. CTIO1m / Y4KCam, 4 amps). Single-amp
instruments like Nickel have no crosstalk and need none of this.

## How it works

```
profile.crosstalk (CrosstalkSpec)  ─┐
                                    ├─► CrosstalkCalib ─► certify ─► {prefix}/calib/crosstalk
stips measure-crosstalk (cp_pipe) ──┘                                   │ (chained into
                                                                        │  {prefix}/calib/curated)
                                                                        ▼
                                                          ISR doCrosstalk=True applies it
```

The certified calib lives in `{prefix}/calib/crosstalk`, chained into the curated
calib chain that ISR already reads. **Butler is the source of truth for the applied
calib** — both the declarative and measured paths land there. When a profile
declares `crosstalk`, STIPS injects `isr:doCrosstalk=True` into every ISR call (so
the master bias/flat and the science frames are corrected consistently).

## Declaring coefficients

Add a `CrosstalkSpec` to the instrument profile (`instruments/<name>/profile.py`):

```python
from stips import CrosstalkSpec

profile = InstrumentProfile(
    ...,
    crosstalk=CrosstalkSpec(
        coeffs=[
            [0.0,   1e-4, 2e-4, 3e-4],
            [3e-4,  0.0,  2e-4, 1e-4],
            [4e-4,  5e-4, 0.0,  6e-4],
            [7e-4,  8e-4, 9e-4, 0.0 ],
        ],
        units="adu",   # or "electron"
    ),
)
```

**Matrix convention** (matches LSST): `coeffs[i][j]` is the fraction of amplifier
`j`'s signal that appears in amplifier `i`. Amp index `i` corresponds to
`detector.getAmplifiers()[i]` — i.e. the camera's amp order (`A00, A01, …`). The
diagonal is zero. The matrix must be square with dimension equal to the number of
amplifiers; this is checked at build time against the camera.

A **zero matrix is a valid no-op** placeholder: it exercises the full
build→certify→ISR path without changing pixels, which is how CTIO1m / Y4KCam ships
until real coefficients exist.

The calib is built and certified automatically as part of `stips calibs` /
`stips run` (inside `write-curated-calibrations`), so no extra step is needed once
the matrix is declared.

## Measuring coefficients

If you have no known coefficients, measure them from data:

```bash
stips -p ctio1m measure-crosstalk 20070321 20070322
```

This runs cp_pipe's `cpCrosstalk` pipeline (ISR → extract → solve) over the given
nights' **science** frames, certifies the resulting matrix into the calib chain,
and exports it to `REPO/crosstalk/<instrument>_crosstalk.ecsv` for inspection
(use `--export-dir` to change the location). Run it once, typically right after
your first `stips calibs`.

Requirements and tips:
- **Bias calibs must exist first** — the measurement ISR applies bias. Run
  `stips calibs <night>` before measuring.
- Works best with frames containing **bright sources** that span amplifier
  boundaries (cp_pipe's extractor thresholds bright pixels). ~8+ exposures is a
  good target.
- The measurement ISR does **not** apply crosstalk while measuring it, but does
  reuse the profile's `isr_overrides` (e.g. overscan handling) for consistency.
- If too few bright sources are found the solve can return a near-zero/invalid
  matrix; inspect the exported ECSV before trusting it.

Once measured, you can paste the values from the exported ECSV into the profile's
`CrosstalkSpec` to version-control them (the export path itself is informational —
it is not a Butler discovery location).

## Disabling crosstalk

Leave `crosstalk=None` (the default) in the profile. ISR `doCrosstalk` stays off
and no crosstalk calib is built. To explicitly force it off even when a matrix is
present, set `isr_overrides={"doCrosstalk": False}` (an explicit override wins over
the automatic injection).

## Collections

| Collection | Type | Purpose |
|------------|------|---------|
| `{prefix}/calib/crosstalk/gen/{ts}` | RUN | Freshly built/measured calib (pre-certification) |
| `{prefix}/calib/crosstalk` | CALIBRATION | Certified crosstalk, chained into the curated chain |
| `{prefix}/calib/curated` | CHAINED | Curated calibs (defects + crosstalk), read by ISR |
