<img src="docs/_static/stips_logo.svg" alt="STIPS logo" width="250">

# STIPS

[![CI](https://github.com/dangause/stips/actions/workflows/ci.yml/badge.svg)](https://github.com/dangause/stips/actions/workflows/ci.yml)
[![Docs](https://readthedocs.org/projects/stips-docs/badge/?version=latest)](https://stips-docs.readthedocs.io/en/latest/)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23243456.svg)](https://doi.org/10.5281/zenodo.23243456)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](pyproject.toml)

STIPS, the Small Telescope Image Processing Suite, reduces imaging from
1-meter class telescopes with the Rubin Observatory's
[LSST Science Pipelines](https://pipelines.lsst.io/). One YAML file per target
takes raw frames to calibrated lightcurves: calibration, astrometry and
photometry, image subtraction, forced photometry, and period or transit
searches.

Check out our [ReadTheDocs site](https://stips-docs.readthedocs.io/en/latest/)
for more information on
[installation](https://stips-docs.readthedocs.io/en/latest/installation.html),
the [quickstart](https://stips-docs.readthedocs.io/en/latest/quickstart.html),
configuration, and the
[CLI reference](https://stips-docs.readthedocs.io/en/latest/reference/cli.html).

Supported instruments:

* Nickel 1-m at Lick Observatory
  ([docs](https://stips-docs.readthedocs.io/en/latest/instruments/nickel/index.html))
* CTIO 1.0-m / Y4KCam
  ([docs](https://stips-docs.readthedocs.io/en/latest/instruments/ctio1m/index.html))
* Any similar telescope, by describing its camera in a profile directory. See
  [Adding a telescope](https://stips-docs.readthedocs.io/en/latest/forking-stips.html).

## Contributing

See the [development guide](https://stips-docs.readthedocs.io/en/latest/development.html)
for setup instructions, tests, and contribution practices. Questions and bug
reports are welcome on the [issue tracker](https://github.com/dangause/stips/issues).

## Citation

If you use STIPS in your work, please cite it through its Zenodo record,
[10.5281/zenodo.23243456](https://doi.org/10.5281/zenodo.23243456), and also
cite the LSST Science Pipelines it is built on. See
[Citing STIPS](https://stips-docs.readthedocs.io/en/latest/citing.html) for
details.

Find full citation information [here](./CITATION.cff).

## License

STIPS is distributed under the [BSD 3-Clause License](LICENSE). Releases up
to and including v2.4.0 were distributed under GPL-3.0-or-later and remain
under that license.

The Lick archive client vendored in
`instruments/nickel/vendor/lick_searchable_archive/` is distributed under its
own BSD 3-Clause license (Copyright 2022 UC Observatories); see
[its LICENSE](instruments/nickel/vendor/lick_searchable_archive/LICENSE).

### Notice

STIPS runs on the LSST Science Pipelines, and the tasks in `obs_stips`
subclass classes from them. The pipelines are distributed under their own
licenses, largely GPL-3.0. The STIPS container images bundle the pipelines, so
the images as a whole are also subject to the pipelines' licenses.

One file, `packages/obs_stips/python/lsst/obs/stips/calibCombine.py`, contains
code derived from cp_pipe and is distributed under GPL-3.0-or-later; see its
header.

## Acknowledgements

STIPS is built on the LSST Science Pipelines. Thanks to the Rubin Observatory
Data Management team for the infrastructure and documentation.
