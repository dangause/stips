#!/usr/bin/env python3
"""Download Nickel raws for an observing night from the Lick searchable archive.

This pulls files into the layout expected by obs_nickel ingestion:
  ${RAW_PARENT_DIR}/${NIGHT}/raw/<archive-relative-path>.fits

Usage:
  obsn-archive-fetch-night --night YYYYMMDD [--raw-root PATH] [--archive-url URL]
  # or via module invocation
  python -m obs_nickel_data_tools.pipeline_tools.fetch_archive_night --night YYYYMMDD [--raw-root PATH] [--archive-url URL]

Environment defaults:
  RAW_PARENT_DIR      root for raw data (same as used by nickel calibs)
  LICK_ARCHIVE_URL    archive API base (default https://archive.ucolick.org/archive)
  LICK_ARCHIVE_DIR    path to the lick_searchable_archive repo to put on PYTHONPATH
  LICK_ARCHIVE_INSTR  instrument filter to pass to the API (default NICKEL)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - py<3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore


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
            "Set LICK_ARCHIVE_DIR or use --client-path to point at the "
            "lick_searchable_archive clone, or pip install -e that repo."
        )
        raise SystemExit(msg) from err
    return LickArchiveClient, QueryTerm


def _daterange_for_night(night: str, timezone: str) -> tuple[dt.datetime, dt.datetime]:
    """Return [local-noon, next-local-noon) window for an observing night."""
    tz = ZoneInfo(timezone)
    try:
        date = dt.datetime.strptime(night, "%Y%m%d").date()
    except ValueError as err:  # pragma: no cover - CLI validation
        raise SystemExit(f"Invalid --night '{night}' (use YYYYMMDD)") from err
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Nickel raws for a night into RAW_PARENT_DIR/night/raw"
    )
    parser.add_argument(
        "--night", required=True, help="Observing night YYYYMMDD (local Lick date)"
    )
    parser.add_argument(
        "--raw-root",
        default=os.environ.get("RAW_PARENT_DIR"),
        help="Root directory for raws (default: $RAW_PARENT_DIR)",
    )
    parser.add_argument(
        "--archive-url",
        default=os.environ.get(
            "LICK_ARCHIVE_URL", "https://archive.ucolick.org/archive"
        ),
        help="Archive API base URL",
    )
    parser.add_argument(
        "--client-path",
        default=os.environ.get("LICK_ARCHIVE_DIR"),
        help="Path to lick_searchable_archive to add to PYTHONPATH",
    )
    parser.add_argument(
        "--instrument",
        default=os.environ.get("LICK_ARCHIVE_INSTR", "NICKEL_DIR"),
        help="Archive instrument filter value (NICKEL_DIR or NICKEL_SPEC)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Results per page when querying (default 200)",
    )
    parser.add_argument(
        "--timezone",
        default="America/Los_Angeles",
        help="Timezone for night boundaries (default America/Los_Angeles)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download files even if they already exist",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    if not args.raw_root:
        raise SystemExit("Set --raw-root or RAW_PARENT_DIR in your environment.")

    raw_root = Path(args.raw_root).expanduser()
    raw_dir = raw_root / args.night / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    _ensure_client_module(args.client_path)
    LickArchiveClient, QueryTerm = _import_client()

    start, end = _daterange_for_night(args.night, args.timezone)
    logging.info(
        "Night %s window: %s to %s (%s)", args.night, start, end, args.timezone
    )

    # Configure client with rate limiting to avoid 429 errors
    client = LickArchiveClient(
        args.archive_url,
        rate_limit_delay=0.5,  # 500ms between requests
        retry_max_time=300,  # 5 minutes max retry time
        retry_max_delay=60,  # Max 60s exponential backoff
    )
    term = QueryTerm(field="obs_date", value=[start, end])
    filters = {"instrument": args.instrument} if args.instrument else {}

    downloaded = 0
    skipped = 0
    errors = 0

    for results in _iter_pages(client, term, filters, args.page_size):
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

            if dest.exists() and not args.overwrite:
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


if __name__ == "__main__":
    raise SystemExit(main())
