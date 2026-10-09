# STIPS

**STIPS**, the *Small Telescope Image Processing Suite*, reduces imaging from
1-meter class telescopes with the Rubin Observatory's [LSST Science
Pipelines](https://pipelines.lsst.io/). One YAML file per target takes raw
frames to calibrated lightcurves: calibration, astrometry and photometry,
image subtraction, forced photometry, and period or transit searches.

STIPS was built for supernova follow-up with the Nickel 1-m at Lick
Observatory, and supports any similar telescope whose camera is described in
a short profile. {doc}`overview` explains what it does, why it exists, and why
it is built on the Rubin stack.

::::{grid} 1 2 2 2
:gutter: 3

:::{grid-item-card} What is STIPS?
:link: overview
:link-type: doc
Why it exists, what it is for, and why the Rubin stack.
:::

:::{grid-item-card} Install
:link: installation
:link-type: doc
The Rubin stack and STIPS, natively or as one container.
:::

:::{grid-item-card} Quickstart
:link: quickstart
:link-type: doc
Reduce three nights of SN 2023ixf, from archive to lightcurve.
:::

:::{grid-item-card} Add a telescope
:link: forking-stips
:link-type: doc
Describe your camera in a profile directory.
:::
::::

```{toctree}
:maxdepth: 2
:caption: Introduction
:hidden:

What is STIPS? <overview>
How STIPS works <how-it-works>
```

```{toctree}
:maxdepth: 2
:caption: Getting started
:hidden:

Install the Rubin stack <install-rubin-stack>
Install STIPS <installation>
Quickstart <quickstart>
```

```{toctree}
:maxdepth: 2
:caption: User guide
:hidden:

Set up a campaign <new-campaign>
Configuration <configuration>
Templates <templates>
Reference catalogs <reference-catalogs>
Variable stars and transits <time-series>
Science configs <science-configs>
Outputs <outputs>
Logs and debugging <logging>
Running on a cluster <hpc>
Troubleshooting <troubleshooting>
```

```{toctree}
:maxdepth: 2
:caption: Instruments
:hidden:

Adding a telescope <forking-stips>
How profiles become instruments <obs-abstraction>
Instrument tests <instrument-contract>
Crosstalk <crosstalk>
```

```{toctree}
:maxdepth: 2
:caption: Developer guide
:hidden:

Development <development>
Code architecture <architecture>
Cluster architecture <architecture-bps-docker-slurm>
Stack upgrades <stack-bump-runbook>
Refcat validation <refcat-validation-runbook>
Migrations <migrations>
```

```{toctree}
:maxdepth: 2
:caption: Validation reports
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
