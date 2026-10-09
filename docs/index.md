# STIPS

**STIPS** — the *Small Telescope Image Processing Suite* — brings the
[LSST Science Pipelines](https://pipelines.lsst.io/) to 1-meter class
telescopes. It runs survey-grade calibration, difference imaging, forced
photometry, and lightcurve extraction on small-telescope data without deep
LSST middleware knowledge. Its main use is transient astronomy: supernova
monitoring campaigns at the Nickel 1-m at Lick Observatory.

STIPS has three parts. The **`stips` CLI** runs every step, from calibration
through difference imaging to lightcurves, from one YAML config.
**`obs_stips`** turns an instrument profile into an LSST instrument at runtime
and ships the default pipelines and configs. An **instrument profile** is a
directory, `instruments/<name>/`, that describes one telescope, so adding a
telescope means adding a directory rather than a package. STIPS supports the
Nickel 1-m and the CTIO 1.0-m with Y4KCam, and targets LSST Science Pipelines
release `v30_0_3`. See {doc}`architecture`.

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} Get started
:link: getting-started
:link-type: doc
Install STIPS and run a first pipeline.
:::

:::{grid-item-card} Run a campaign
:link: new-campaign
:link-type: doc
Target, nights, template strategy, and the one-command run.
:::

:::{grid-item-card} Add a telescope
:link: forking-stips
:link-type: doc
A declarative profile directory for your own 1-m.
:::

:::{grid-item-card} CLI reference
:link: reference/cli
:link-type: doc
Every command and option, from `--help`.
:::
::::

```{toctree}
:maxdepth: 2
:caption: Getting started
:hidden:

Installation and first run <getting-started>
New campaign <new-campaign>
```

```{toctree}
:maxdepth: 2
:caption: Guide
:hidden:

Configuration <configuration>
Science configs <science-configs>
Logging <logging>
Troubleshooting <troubleshooting>
Architecture <architecture>
```

```{toctree}
:maxdepth: 2
:caption: Instruments
:hidden:

Adding a telescope <forking-stips>
Instrument contract <instrument-contract>
Instrument abstraction <obs-abstraction>
Crosstalk <crosstalk>
```

```{toctree}
:maxdepth: 2
:caption: Operations
:hidden:

HPC, Docker, and Slurm <architecture-bps-docker-slurm>
Stack-bump runbook <stack-bump-runbook>
Refcat validation <refcat-validation-runbook>
Migrations <migrations>
```

```{toctree}
:maxdepth: 2
:caption: Validation
:hidden:

SkyMapper templates <skymapper-template-validation>
Template colour terms <template-colorterm-fit>
```

```{toctree}
:maxdepth: 2
:caption: Reference
:hidden:

CLI reference <reference/cli>
Python API <reference/python-api>
Changelog <changelog>
Citing STIPS <citing>
```
