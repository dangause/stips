# Configuration loader

`stips.core.config` turns a YAML file's `env:` block into a validated
`Config`, loads the active instrument profile from `INSTRUMENT_DIR`, and
resolves pipelines and config overrides instrument-dir-first. See
[Configuration](../../configuration.md) for the file format.

::: stips.core.config
