# obs-nickel-refcats

Home for reference catalog manifests and helpers. Large refcat bundles should be
stored externally (S3, Google Cloud Storage, etc.) and referenced via
`data-manifests/refcats.yaml`; this package provides the glue code for ingest
and validation.

Reference catalog scripts are in `packages/refcats/scripts/` and source code is in
`packages/refcats/src/nickel_refcats/`.

Install editable from the repo root if you add helpers here:

```bash
python -m pip install -e packages/refcats
```
