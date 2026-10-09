# Development

## Set up

```bash
git clone https://github.com/dangause/stips.git && cd stips
git lfs pull                 # test fixtures are stored with Git LFS
uv sync --all-groups         # STIPS and every dependency group
pre-commit install
```

## Tests

```bash
uv run pytest -q                          # the tests that run without the stack
STACK_DIR=/path/to/lsst_stack make test   # the full suite, with the stack set up
```

Tests live in `packages/*/tests/` and `instruments/*/tests/`. Tests that need
the stack skip themselves when it is not set up; with it, the suite also
checks that every pipeline YAML builds a quantum graph. CI runs the full suite
in Rubin's container against the weekly `w_2025_32`. A weekly scheduled job
runs the stack-API and pipeline-graph tests against the latest weekly, to
catch breakage before the pin moves.

## Style

`make lint` runs ruff and `make format` formats the code. The pre-commit
hooks run ruff, black, and file checks on each commit; CI runs them on every
file.

## Documentation

The site is MyST Markdown in `docs/`, built with Sphinx and the furo theme
and published on Read the Docs.

```bash
make docs          # build into docs/_build/html, failing on any warning
make docs-serve    # live preview at http://127.0.0.1:8000
```

- The sidebar is the set of `toctree` blocks in `docs/index.md`. Add new pages
  there.
- The CLI reference is generated from the click commands by
  `docs/_ext/stips_cli.py`, and the Python API pages by autodoc, so both
  follow the code.
- Internal notes (audits, plans, poster drafts) stay in `docs/` but are
  excluded in `docs/conf.py`.

## Contributing

Branch from `dev` and open a pull request against `dev`. CI must pass: lint,
the test suite in the Rubin container, and the docs build. Note user-visible
changes in `CHANGELOG.md`. To move to another Rubin release, follow the
{doc}`stack-bump-runbook`.
