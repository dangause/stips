#!/usr/bin/env python3
"""Query Lick Observatory archive for data exploration and analysis.

This tool provides exploratory data analysis capabilities for the Lick archive:
- Summary statistics (count, date range, filter distribution)
- Per-night breakdown with metadata
- Target/object catalog
- Optional visualization

Usage:
  obsn-eda-archive summary --start 20200101 --end 20201231
  obsn-eda-archive nights --start 20200101 --end 20201231 [--format csv]
  obsn-eda-archive targets --start 20200101 --end 20201231
  obsn-eda-archive plot-filters --start 20200101 --end 20201231 --output filters.png

Environment:
  LICK_ARCHIVE_URL    archive API base (default https://archive.ucolick.org/archive)
  LICK_ARCHIVE_DIR    path to lick_searchable_archive for PYTHONPATH
  LICK_ARCHIVE_INSTR  instrument filter (default NICKEL_DIR)
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from . import formatters


def _ensure_client_module(extra_path: str | None) -> None:
    """Put lick_searchable_archive on sys.path if needed."""
    if extra_path:
        sys.path.insert(0, extra_path)


def _import_client():
    """Import Lick archive client or exit with helpful message."""
    try:
        from lick_archive.client.lick_archive_client import (  # type: ignore
            LickArchiveClient,
            QueryTerm,
        )
    except ImportError as err:
        msg = (
            f"Could not import lick_archive client (ImportError: {err}). "
            "Set LICK_ARCHIVE_DIR or use --client-path to point at the "
            "lick_searchable_archive clone."
        )
        raise SystemExit(msg) from err
    return LickArchiveClient, QueryTerm


def _parse_date(date_str: str) -> dt.date:
    """Parse YYYYMMDD string to date."""
    try:
        return dt.datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError as err:
        raise SystemExit(f"Invalid date '{date_str}' (use YYYYMMDD)") from err


def _daterange_for_query(
    start: str, end: str, timezone: str = "America/Los_Angeles"
) -> tuple[dt.date, dt.date]:
    """Return date range covering all observing nights in the period.

    Parameters
    ----------
    start : str
        Start night YYYYMMDD (inclusive)
    end : str
        End night YYYYMMDD (inclusive)
    timezone : str
        Timezone for night boundaries (used to determine UTC date boundaries)

    Returns
    -------
    tuple[dt.date, dt.date]
        (start_date, end_date) in YYYY-MM-DD format for archive query
    """
    tz = ZoneInfo(timezone)
    start_date = _parse_date(start)
    end_date = _parse_date(end)

    # For archive queries, we need to convert local observing nights to UTC dates
    # An observing night runs from noon local time to noon the next day
    # We need to find the UTC dates that cover this period

    # Start of first night (noon local time)
    start_dt = dt.datetime.combine(start_date, dt.time(12, 0), tzinfo=tz)
    # End of last night (noon local time the next day)
    end_dt = dt.datetime.combine(
        end_date + dt.timedelta(days=1), dt.time(12, 0), tzinfo=tz
    )

    # Convert to UTC to get the date range in UTC
    start_utc = start_dt.astimezone(dt.UTC).date()
    end_utc = end_dt.astimezone(dt.UTC).date()

    return start_utc, end_utc


def _fetch_all_results(client, term, filters: dict, page_size: int = 200) -> list[dict]:
    """Fetch all paginated results from archive query.

    Parameters
    ----------
    client
        LickArchiveClient instance
    term
        QueryTerm for date range
    filters : dict
        Additional query filters (e.g., instrument)
    page_size : int
        Results per page

    Returns
    -------
    list[dict]
        All query results
    """
    all_results = []
    page = 1

    while True:
        # Request basic metadata
        # Note: archive may only return filename and id; other fields like filter,
        # exptime, airmass may not be indexed and require FITS header inspection
        count, results, _prev, next_url = client.query(
            term,
            filters=filters,
            results=["filename"],  # Only request fields that are definitely available
            page=page,
            page_size=page_size,
        )
        if page == 1:
            logging.info(f"Archive query returned {count} total results")

        if not results:
            break

        all_results.extend(results)

        if not next_url:
            break

        page += 1

    return all_results


def _extract_night_from_filename(filename: str) -> str | None:
    """Extract observing night from archive filename.

    Archive paths typically look like: 2020-12/19/nickel/d16088.fits
    Returns YYYYMMDD format.
    """
    parts = Path(filename).parts
    if len(parts) >= 2:
        try:
            year_month = parts[0]  # "2020-12"
            day = parts[1]  # "19"
            year, month = year_month.split("-")
            return f"{year}{month.zfill(2)}{day.zfill(2)}"
        except (ValueError, IndexError):
            pass
    return None


def cmd_summary(args) -> int:
    """Show summary statistics for archive data."""
    _ensure_client_module(args.client_path)
    LickArchiveClient, QueryTerm = _import_client()

    start_dt, end_dt = _daterange_for_query(args.start, args.end, args.timezone)
    logging.info(f"Querying archive from {start_dt} to {end_dt}")

    client = LickArchiveClient(
        args.archive_url,
        rate_limit_delay=0.5,
        retry_max_time=300,
        retry_max_delay=60,
    )

    term = QueryTerm(field="obs_date", value=[start_dt, end_dt])
    filters = {"instrument": args.instrument} if args.instrument else {}

    results = _fetch_all_results(client, term, filters, args.page_size)

    if not results:
        formatters.print_warning("No results found in archive for specified date range")
        return 1

    # Extract metadata from filenames
    # Archive only returns filename and id; other metadata requires FITS header inspection
    nights = [
        _extract_night_from_filename(r["filename"])
        for r in results
        if r.get("filename")
    ]
    nights = [n for n in nights if n]

    # Compute statistics
    formatters.print_section("Archive Summary Statistics")
    formatters.print_info("Total exposures", len(results))
    formatters.print_info("Observing nights", len(set(nights)) if nights else "Unknown")

    if nights:
        sorted_nights = sorted(set(nights))
        formatters.print_info(
            "Night range", f"{sorted_nights[0]} to {sorted_nights[-1]}"
        )

    formatters.print_section("Note", style="bold yellow")
    print("  Archive metadata (filter, exptime, object, etc.) is not indexed.")
    print("  For detailed analysis, download files and inspect FITS headers.")
    print("  Use 'nights' command to see per-night file counts.")

    return 0


def cmd_nights(args) -> int:
    """Show per-night breakdown of observations."""
    _ensure_client_module(args.client_path)
    LickArchiveClient, QueryTerm = _import_client()

    start_dt, end_dt = _daterange_for_query(args.start, args.end, args.timezone)

    client = LickArchiveClient(
        args.archive_url,
        rate_limit_delay=0.5,
        retry_max_time=300,
        retry_max_delay=60,
    )

    term = QueryTerm(field="obs_date", value=[start_dt, end_dt])
    filters = {"instrument": args.instrument} if args.instrument else {}

    results = _fetch_all_results(client, term, filters, args.page_size)

    if not results:
        formatters.print_warning("No results found")
        return 1

    # Group by night - only filename is available
    nights_data: dict[str, int] = defaultdict(int)

    for r in results:
        night = _extract_night_from_filename(r.get("filename", ""))
        if not night:
            continue
        nights_data[night] += 1

    # Format for output
    table_data = []
    for night in sorted(nights_data.keys()):
        table_data.append(
            {
                "Night": night,
                "File_Count": nights_data[night],
            }
        )

    formatters.output_data(
        table_data,
        format_type=args.format,
        output_file=args.output,
        title="Archive Files by Night",
        column_order=["Night", "File_Count"],
    )

    return 0


def _cmd_targets_not_implemented(args) -> int:
    """Target catalog requires FITS header metadata not available in archive index."""
    formatters.print_error(
        "Target and filter analysis requires FITS header inspection.\\n"
        "The archive index only provides filenames.\\n"
        "Download files with 'obsn-archive-fetch-night' and analyze locally."
    )
    return 1


def cmd_targets(args) -> int:
    """Show target/object catalog - not available via archive index."""
    formatters.print_error(
        "Target catalog analysis requires FITS header metadata.\n"
        "The archive index only provides filenames.\n"
        "Download files with 'obsn-archive-fetch-night' and analyze FITS headers locally."
    )
    return 1


def cmd_plot_filters(args) -> int:
    """Generate filter visualization - not available via archive index."""
    formatters.print_error(
        "Filter usage analysis requires FITS header metadata.\n"
        "The archive index only provides filenames.\n"
        "Download files with 'obsn-archive-fetch-night' and analyze FITS headers locally."
    )
    return 1


def _cmd_plot_filters_original(args) -> int:
    """Original implementation - kept for reference."""
    _ensure_client_module(args.client_path)
    LickArchiveClient, QueryTerm = _import_client()

    start_dt, end_dt = _daterange_for_query(args.start, args.end, args.timezone)

    client = LickArchiveClient(
        args.archive_url,
        rate_limit_delay=0.5,
        retry_max_time=300,
        retry_max_delay=60,
    )

    term = QueryTerm(field="obs_date", value=[start_dt, end_dt])
    filters = {"instrument": args.instrument} if args.instrument else {}

    results = _fetch_all_results(client, term, filters, args.page_size)

    if not results:
        formatters.print_warning("No results found")
        return 1

    # Extract data for plotting
    df_data = []
    for r in results:
        night = _extract_night_from_filename(r.get("filename", ""))
        if not night or not r.get("filter"):
            continue

        df_data.append(
            {
                "night": night,
                "filter": r["filter"],
            }
        )

    if not df_data:
        formatters.print_warning("No filter data found for plotting")
        return 1

    df = pd.DataFrame(df_data)

    # Create visualization
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Filter distribution pie chart
    filter_counts = df["filter"].value_counts()
    ax1.pie(
        filter_counts.values,
        labels=filter_counts.index,
        autopct="%1.1f%%",
        startangle=90,
    )
    ax1.set_title("Filter Distribution")

    # Plot 2: Filter usage over time
    nights_sorted = sorted(df["night"].unique())
    filter_by_night = df.groupby(["night", "filter"]).size().unstack(fill_value=0)

    filter_by_night = filter_by_night.reindex(nights_sorted, fill_value=0)

    # Stacked bar chart
    filter_by_night.plot(kind="bar", stacked=True, ax=ax2)
    ax2.set_title("Filter Usage Over Time")
    ax2.set_xlabel("Observing Night")
    ax2.set_ylabel("Number of Exposures")
    ax2.legend(title="Filter", bbox_to_anchor=(1.05, 1), loc="upper left")

    # Rotate x-axis labels for readability
    ax2.tick_params(axis="x", rotation=45)

    # Only show every Nth label if there are many nights
    if len(nights_sorted) > 20:
        step = len(nights_sorted) // 20
        ax2.set_xticks(range(0, len(nights_sorted), step))
        ax2.set_xticklabels(
            [nights_sorted[i] for i in range(0, len(nights_sorted), step)]
        )

    plt.tight_layout()

    if args.output:
        plt.savefig(args.output, dpi=150, bbox_inches="tight")
        formatters.print_info("Plot saved to", args.output)
    else:
        plt.show()

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Explore Lick Observatory archive data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    # Common arguments for all subcommands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--start",
        required=True,
        help="Start night YYYYMMDD (inclusive)",
    )
    common_parser.add_argument(
        "--end",
        required=True,
        help="End night YYYYMMDD (inclusive)",
    )
    common_parser.add_argument(
        "--archive-url",
        default=os.environ.get(
            "LICK_ARCHIVE_URL", "https://archive.ucolick.org/archive"
        ),
        help="Archive API base URL",
    )
    common_parser.add_argument(
        "--client-path",
        default=os.environ.get("LICK_ARCHIVE_DIR"),
        help="Path to lick_searchable_archive to add to PYTHONPATH",
    )
    common_parser.add_argument(
        "--instrument",
        default=os.environ.get("LICK_ARCHIVE_INSTR", "NICKEL_DIR"),
        help="Archive instrument filter",
    )
    common_parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Results per page (default 200)",
    )
    common_parser.add_argument(
        "--timezone",
        default="America/Los_Angeles",
        help="Timezone for night boundaries",
    )

    subparsers = parser.add_subparsers(dest="command", help="EDA command")

    # Summary command
    subparsers.add_parser(
        "summary",
        parents=[common_parser],
        help="Show summary statistics",
    )

    # Nights command
    parser_nights = subparsers.add_parser(
        "nights",
        parents=[common_parser],
        help="Show per-night breakdown",
    )
    parser_nights.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_nights.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    # Targets command
    parser_targets = subparsers.add_parser(
        "targets",
        parents=[common_parser],
        help="Show target/object catalog",
    )
    parser_targets.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_targets.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    # Plot filters command
    parser_plot = subparsers.add_parser(
        "plot-filters",
        parents=[common_parser],
        help="Visualize filter usage",
    )
    parser_plot.add_argument(
        "--output",
        help="Output file (show interactive plot if not specified)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    # Dispatch to command handler
    if args.command == "summary":
        return cmd_summary(args)
    elif args.command == "nights":
        return cmd_nights(args)
    elif args.command == "targets":
        return cmd_targets(args)
    elif args.command == "plot-filters":
        return cmd_plot_filters(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
