# stips-refcats

Instrument-neutral reference-catalog helpers for STIPS: Gaia/PS1 cone fetch,
HTM trixel coverage math, and LSST `convertReferenceCatalog` conversion configs.

Source code is in `packages/refcats/src/stips_refcats/`; the
`convertReferenceCatalog` config files are shipped as package data under
`packages/refcats/src/stips_refcats/configs/`. Additional fetch/convert helper
scripts live in `packages/refcats/scripts/`.

The legacy import name `nickel_refcats` still works as a thin compatibility
shim (it re-exports `stips_refcats` and emits a `DeprecationWarning`); import
`stips_refcats` in new code.

## Venv-safe by design

The cone **fetch** runs in a plain venv: the package declares its fetch
dependencies (`astroquery`, `astropy`, `numpy`, `pandas`), so a clean
`uv sync --group dev` can pull Gaia DR3 / PS1 DR2 cones with no LSST stack.

The two operations that genuinely need the stack — HTM trixel coverage math
(`lsst.geom`/`meas_algorithms`) and `convertReferenceCatalog` — are called
through STIPS's stack wrapper (`stips.core.refcat`), which tries the in-process
path first and falls back to running the identical computation in-stack when
`lsst` isn't importable. So `stips run` with `refcat.mode: gaia_ps1` fetches,
converts, and ingests the exact cone it needs on demand **without a
stack-activated shell** (`STACK_DIR` must still point at a valid stack for the
in-stack fallback). No RSP / MONSTER required.

Install editable from the repo root if you add helpers here:

```bash
python -m pip install -e packages/refcats
```
