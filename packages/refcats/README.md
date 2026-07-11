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

Install editable from the repo root if you add helpers here:

```bash
python -m pip install -e packages/refcats
```
