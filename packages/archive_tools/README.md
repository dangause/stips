# obs-nickel-archive-tools

Python CLIs that support the Nickel pipelines: archive downloads, PS1 template
ingest, DIA QA helpers, and skymap utilities. These files used to live under
`scripts/python/pipeline_tools` and `scripts/python/skymap`; the original paths
remain as thin wrappers that import this package so existing shell scripts keep
working.

## Usage

Install editable from the repo root:

```bash
python -m pip install -e packages/archive_tools
```

Then invoke via entrypoints (or continue using the legacy paths):

- `obsn-archive-fetch-night --night 20210101 --raw-root ...`
- `obsn-archive-nights --start 20210101 --end 20210110 -o nights.txt`
- `obsn-archive-ingest-ps1 ...`
- `obsn-dia-assess --repo ... --collection ...`
- `obsn-dia-lightcurve --repo ... --collection ... --ra ... --dec ...`
- `obsn-skymap-build-config ...`
- `obsn-skymap-make ...`

LSST stack dependencies are expected to be available in the environment; only
common Python deps are declared here.
