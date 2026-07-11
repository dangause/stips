"""Nickel Lick-archive raw-data fetch (implements the ``fetch_data`` hook).

This is the Nickel-specific implementation of the framework's
``InstrumentProfile.fetch_data`` hook. It downloads a night's raw frames from
the Lick searchable archive into the layout expected by Nickel ingestion:

  ${RAW_PARENT_DIR}/${NIGHT}/raw/<filename>.fits

The ``lick_archive`` client is a heavy, optional dependency, so it is
lazy-imported inside ``_import_client`` rather than at module import time. The
module level stays stdlib-only so that importing the Nickel profile (which wires
``fetch_data``) never drags in the archive client or the LSST stack.

Lick-specific settings are read from the framework config's generic ``env``
block (``LICK_ARCHIVE_DIR``, ``LICK_ARCHIVE_URL``, ``LICK_ARCHIVE_INSTR``).

Only the Lick backend (``_fetch_night``) and this env schema live here; the
``fetch_data`` wrapper (env read, night validation, status mapping) is the
shared framework scaffolding in :mod:`stips.fetch`.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Iterable

from stips.fetch import make_fetch_data, parse_night

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - py<3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore

_DEFAULT_ARCHIVE_URL = "https://archive.ucolick.org/archive"
_DEFAULT_INSTR = "NICKEL_DIR"
_DEFAULT_TZ = "America/Los_Angeles"


def _ensure_client_module(extra_path: str | None) -> None:
    """Put lick_searchable_archive on sys.path if requested."""
    if extra_path:
        sys.path.insert(0, extra_path)


def _import_client():
    try:
        from lick_archive.client.lick_archive_client import (  # type: ignore
            LickArchiveClient,
            QueryTerm,
        )
    except ImportError as err:
        msg = (
            f"Could not import lick_archive client (ImportError: {err}). "
            "Set LICK_ARCHIVE_DIR in the config env: block to point at the "
            "lick_searchable_archive clone, or pip install -e that repo."
        )
        raise ImportError(msg) from err
    return LickArchiveClient, QueryTerm


def _daterange_for_night(night: str, timezone: str) -> tuple[dt.datetime, dt.datetime]:
    """Return [local-noon, next-local-noon) window for an observing night."""
    tz = ZoneInfo(timezone)
    date = parse_night(night)
    start = dt.datetime.combine(date, dt.time(12, 0), tzinfo=tz)
    return start, start + dt.timedelta(days=1)


def _iter_pages(client, term, filters, page_size: int) -> Iterable[list[dict]]:
    """Yield pages of query results until exhausted."""
    page = 1
    while True:
        count, results, _prev, next_url = client.query(
            term,
            filters=filters,
            results=["filename", "object", "obs_date"],
            page=page,
            page_size=page_size,
        )
        if page == 1:
            logging.info("Archive query returned %s results", count)
        if not results:
            break
        yield results
        if not next_url:
            break
        page += 1


def _fetch_night(
    night: str,
    raw_root: Path,
    *,
    client_path: str | None,
    archive_url: str,
    instrument: str,
    timezone: str = _DEFAULT_TZ,
    page_size: int = 200,
    overwrite: bool = False,
) -> int:
    """Download a night's raws from the Lick archive.

    Returns an int status code (NOT via ``sys.exit``):
      0 -> data downloaded and/or already present (ok)
      1 -> hard failure (one or more download errors)
      2 -> no data found in the archive for this night
    """
    raw_root = Path(raw_root).expanduser()
    raw_dir = raw_root / night / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    _ensure_client_module(client_path)
    LickArchiveClient, QueryTerm = _import_client()

    start, end = _daterange_for_night(night, timezone)
    logging.info("Night %s window: %s to %s (%s)", night, start, end, timezone)

    # Configure client with rate limiting to avoid 429 errors
    client = LickArchiveClient(
        archive_url,
        rate_limit_delay=0.5,  # 500ms between requests
        retry_max_time=300,  # 5 minutes max retry time
        retry_max_delay=60,  # Max 60s exponential backoff
    )
    term = QueryTerm(field="obs_date", value=[start, end])
    filters = {"instrument": instrument} if instrument else {}

    downloaded = 0
    skipped = 0
    errors = 0

    for results in _iter_pages(client, term, filters, page_size):
        for row in results:
            filename = row.get("filename")
            if not filename:
                logging.warning("Skipping result without filename: %s", row)
                continue
            rel = Path(filename)
            if rel.is_absolute() or ".." in rel.parts:
                logging.warning("Skipping suspicious path: %s", filename)
                continue

            # Strip date-based subdirectories from archive path
            # Archive returns paths like "2020-12/19/nickel/d16088.fits"
            # We want just the filename: "d16088.fits"
            # This avoids duplicate nested directory structure
            dest = raw_dir / rel.name
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists() and not overwrite:
                skipped += 1
                continue
            try:
                ok = client.download(filename, dest)
            except Exception as err:  # pragma: no cover - network errors
                errors += 1
                logging.error("Download failed for %s: %s", filename, err)
                continue
            if ok:
                downloaded += 1
            else:
                errors += 1

    logging.info(
        "Done. downloaded=%s skipped=%s errors=%s -> %s",
        downloaded,
        skipped,
        errors,
        raw_dir,
    )
    if errors > 0:
        return 1  # Hard failure
    if downloaded == 0 and skipped == 0:
        logging.warning("No files found in archive for this night")
        return 2  # No data available
    return 0


def _build_kwargs(env: dict) -> dict:
    """Map the generic config ``env`` block onto ``_fetch_night`` kwargs.

    This is the Nickel/Lick env schema: ``LICK_ARCHIVE_DIR`` (client path, may be
    absent), ``LICK_ARCHIVE_URL`` and ``LICK_ARCHIVE_INSTR`` (with defaults).
    """
    return {
        "client_path": env.get("LICK_ARCHIVE_DIR"),
        "archive_url": env.get("LICK_ARCHIVE_URL", _DEFAULT_ARCHIVE_URL),
        "instrument": env.get("LICK_ARCHIVE_INSTR", _DEFAULT_INSTR),
    }


# InstrumentProfile.fetch_data hook: downloads a night's raws into
# ${RAW_PARENT_DIR}/<night>/raw/ and returns "ok" | "not_found" | "failed".
# The wrapper (env read, night validation, status mapping) is shared framework
# scaffolding; only the Lick backend + env schema above are Nickel-specific.
fetch_data = make_fetch_data(_fetch_night, _build_kwargs)
