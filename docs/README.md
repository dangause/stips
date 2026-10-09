# STIPS documentation

These pages are published at <https://stips-lsst.readthedocs.io>. They are
MyST Markdown, built with Sphinx (`docs/conf.py`); preview them locally with
`make docs-serve`.

| Start here | |
|---|---|
| [What is STIPS?](overview.md) | Why it exists, what it is for, and why the Rubin stack |
| [Install the Rubin stack](install-rubin-stack.md) | The LSST Science Pipelines, release `v30_0_3` |
| [Install STIPS](installation.md) | Native install or the container |
| [Quickstart](quickstart.md) | Three nights of SN 2023ixf, from archive to lightcurve |

The site's sidebar, which lists every page in order, is the set of `toctree`
blocks in [`index.md`](index.md).

## Contributing to the docs

1. Edit or add Markdown files here.
2. Add new user-facing pages to a toctree in `index.md`.
3. Check the build with `make docs`, which fails on any warning, as Read the
   Docs does.
4. Open a pull request against `dev`.

Working notes that are not part of the site (audits, plans, one-off findings)
also live in this folder; `docs/conf.py` excludes them from the build.
