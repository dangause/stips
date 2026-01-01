# obs-nickel (instrument package)

This directory now contains only the obs package assets (camera model, configs,
pipelines, EUPS metadata, and Python code under `python/lsst/obs/nickel`).
Everything else (pipeline runners, archive helpers, data manifests) lives
alongside it in the monorepo. Use the repo root as `OBS_NICKEL` for scripts;
the legacy top-level symlinks remain for compatibility.

Install editable from the repo root:

```bash
python -m pip install -e packages/obs_nickel
```

EUPS users can still `eups declare -r /path/to/repo obs_nickel -t current`
because `ups/` is symlinked at the top level.
