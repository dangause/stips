# Citing STIPS

If you use STIPS in your research, please cite it, and also cite the LSST
Science Pipelines it is built on.

STIPS is archived on Zenodo:

- **All versions** (concept DOI, resolves to the latest release):
  [10.5281/zenodo.23243456](https://doi.org/10.5281/zenodo.23243456)
- **v2.4.0**:
  [10.5281/zenodo.23320419](https://doi.org/10.5281/zenodo.23320419)
- **v2.3.0**:
  [10.5281/zenodo.23270726](https://doi.org/10.5281/zenodo.23270726)
- **v2.2.4**:
  [10.5281/zenodo.23243457](https://doi.org/10.5281/zenodo.23243457)

Cite the version you used. The repository's
[`CITATION.cff`](https://github.com/dangause/stips/blob/main/CITATION.cff)
has the full metadata, and GitHub's "Cite this repository" button exports it
as BibTeX or APA.

## LSST Science Pipelines

- Jurić, M., et al. 2017, "The LSST Data Management System", ASP Conference
  Series 512, *Astronomical Data Analysis Software and Systems XXV*, 279
- Bosch, J., et al. 2018, "The Hyper Suprime-Cam software pipeline", PASJ, 70,
  S5, [doi:10.1093/pasj/psx080](https://doi.org/10.1093/pasj/psx080)

## License

STIPS is distributed under the
[BSD 3-Clause License](https://github.com/dangause/stips/blob/main/LICENSE).
Releases up to and including v2.4.0 were distributed under GPL-3.0-or-later
and remain under that license.

The Lick archive client vendored in
`instruments/nickel/vendor/lick_searchable_archive/` is distributed under its
own BSD 3-Clause license (Copyright 2022 UC Observatories).

STIPS runs on the LSST Science Pipelines, and the tasks in `obs_stips`
subclass classes from them. The pipelines are distributed under their own
licenses, largely GPL-3.0. The STIPS container images bundle the pipelines, so
the images as a whole are also subject to the pipelines' licenses.

One file, `packages/obs_stips/python/lsst/obs/stips/calibCombine.py`, contains
code derived from cp_pipe and is distributed under GPL-3.0-or-later; see its
header.
