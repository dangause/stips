# obs-nickel-defects

Defect generation CLI plus the produced defect masks for Nickel. The legacy path
`scripts/python/defects_tools/defects/make_defects_from_flats.py` now resolves to
this package via symlink, so existing pipeline scripts continue to work.

Usage (editable install):

```bash
python -m pip install -e packages/defects
obsn-defects-from-flats --help
```

LSST stack dependencies (e.g., `lsst.daf.butler`, `lsst.ip.isr`) are expected to
be provided by your environment; only common Python deps are declared here.
