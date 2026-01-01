# obs-nickel-testdata

Minimal, fast fixtures for testing Nickel code. Keep only small, deterministic
samples here; heavier datasets should live in external bundles referenced by the
data manifests. The upstream `testdata_nickel` tree is mirrored under
`packages/testdata/upstream/`.

Install editable from the repo root if you add helpers that need packaging:

```bash
python -m pip install -e packages/testdata
```
