# Python API

STIPS is used through the `stips` CLI, but the modules below are the stable
surface a telescope fork or a contributor works with. All of them import
without the LSST stack.

## Instrument profile (`stips.profile`)

The types a telescope's `instruments/<name>/profile.py` is built from: one
`InstrumentProfile`, the `Site`, `Field`, `CameraSpec`, and `CrosstalkSpec` it
references, and the `@hook` decorator for quirk functions. See
{doc}`../forking-stips`.

```{eval-rst}
.. automodule:: stips.profile
```

## Collection names (`stips.collections`)

Every Butler collection name STIPS reads or writes, parameterized by the
profile's `collection_prefix`. See {doc}`../configuration` for the layout.

```{eval-rst}
.. automodule:: stips.collections
```

## Configuration (`stips.core.config`)

Turns a YAML file's `env:` block into a validated `Config`, loads the active
instrument profile from `INSTRUMENT_DIR`, and resolves pipelines and config
overrides instrument-dir-first.

```{eval-rst}
.. automodule:: stips.core.config
```

## Dataset types (`stips.core.dataset_types`)

Every Butler dataset type name STIPS depends on, so a stack rename is a
one-line change. See {doc}`../stack-bump-runbook`.

```{eval-rst}
.. automodule:: stips.core.dataset_types
```
