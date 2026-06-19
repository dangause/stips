# obs-nickel (instrument package)

This directory now contains only the obs package assets (camera model, configs,
pipelines, EUPS metadata, and Python code under `python/lsst/obs/nickel`).
Everything else (pipeline runners, archive helpers, data manifests) lives
alongside it in the monorepo. Scripts resolve `OBS_NICKEL` via
`scripts/utilities/repo_paths.sh`, so it can point at the repo root or
`packages/obs_nickel`.

Install editable from the repo root:

```bash
python -m pip install -e packages/obs_nickel
```

EUPS users can still `eups declare -r /path/to/nickel_processing_suite/packages/obs_nickel obs_nickel -t current`.
