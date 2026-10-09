# Instrument profile

`stips.profile` holds the types a telescope's `instruments/<name>/profile.py`
is built from: one `InstrumentProfile`, plus the `Site`, `Field`, `CameraSpec`,
and `CrosstalkSpec` it references and the `@hook` decorator for quirk
functions. See [Adding a telescope](../../forking-stips.md) for how they fit
together.

::: stips.profile
