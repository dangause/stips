# Vendored: Lick Observatory Searchable Archive

This directory is a **vendored, locally-modified snapshot** of the Lick
Observatory Searchable Archive (server + Python client). STIPS uses only the
**client** (`lick_archive/client/`), which the Nickel `download` flow imports at
runtime — `instruments/nickel/fetch.py` puts this tree on `sys.path` via the
`LICK_ARCHIVE_DIR` config env var. It is checked in here (rather than pulled as
an external dependency) because upstream is not publicly installable.

## Provenance

- **Project:** Lick Observatory Searchable Archive
- **Upstream (nominal):** `https://github.com/lick-observatory/lick-searchable-archive`
  (per `pyproject.toml [project.urls]`) — **currently unavailable/private; the
  URL 404s.** Homepage: `https://archive.ucolick.org`.
- **Snapshot imported:** 2026-01-01, upstream commit `d62d650`.
- **License:** BSD 3-Clause, "Copyright 2022 UC Observatories" (see `LICENSE`).

## Local modifications

This snapshot is **not** a pristine mirror — it carries STIPS-local enhancements
squashed into the import:

- **Rate-limiting / retry machinery** added to the client
  (`lick_archive/client/lick_archive_client.py`): tenacity-based exponential
  backoff on HTTP 429/5xx, respect for the server's `Retry-After` header, and a
  configurable inter-request delay. See `RATE_LIMITING.md` for details.

## Known upstream rough edges (documented, not fixed here)

- `pyproject.toml` declares `requires-python = ">=3.8"` but the client uses
  PEP 604 (`X | Y`) runtime annotations that raise `TypeError` on 3.8/3.9.
- Mutable default arguments in parts of the public client API.
- `login()` / `logout()` are `NotImplementedError` stubs with aspirational
  docstrings.

## Lint / test scope

The **server** subtree (Django app) is excluded from repo lint/type/test. The
**client** subtree (`lick_archive/client/`) — the only part STIPS depends on —
is un-excluded so it is lint-visible at repo settings (F-035).
