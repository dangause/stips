# obs-nickel-testdata

Minimal, fast fixtures for testing Nickel code. Keep only small, deterministic
samples here; heavier datasets should live in external bundles referenced by the
data manifests.

Test data files are stored in `packages/testdata/data/nickel/raw/`.

Install editable from the repo root if you add helpers that need packaging:

```bash
python -m pip install -e packages/testdata
```
