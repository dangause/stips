#!/usr/bin/env python3
"""
generate_nights_list.py — Generate a nights list file for batch processing

Usage:
    # Generate nights between two dates
    ./generate_nights_list.py --start 20240625 --end 20240630 -o nights.txt

    # Generate specific nights (comma-separated)
    ./generate_nights_list.py --nights 20240625,20240627,20240629 -o nights.txt

    # Auto-discover nights from raw data directory
    ./generate_nights_list.py --auto-discover -o nights.txt

    # Filter by month
    ./generate_nights_list.py --start 20240601 --end 20240630 -o june_2024.txt
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def parse_date(date_str: str) -> datetime:
    """Parse YYYYMMDD string to datetime."""
    try:
        return datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str} (expected YYYYMMDD)")


def generate_date_range(start: str, end: str) -> list[str]:
    """Generate list of nights between start and end dates (inclusive)."""
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    if start_dt > end_dt:
        raise ValueError(f"Start date {start} is after end date {end}")

    nights = []
    current = start_dt
    while current <= end_dt:
        nights.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)

    return nights


def parse_nights_list(nights_str: str) -> list[str]:
    """Parse comma-separated nights list."""
    nights = []
    for night in nights_str.split(","):
        night = night.strip()
        if night:
            # Validate format
            parse_date(night)  # Will raise if invalid
            nights.append(night)
    return nights


def auto_discover_nights(raw_parent_dir: str) -> list[str]:
    """
    Auto-discover nights by scanning RAW_PARENT_DIR for directories
    matching YYYYMMDD pattern.
    """
    parent = Path(raw_parent_dir)
    if not parent.exists():
        raise ValueError(f"RAW_PARENT_DIR not found: {raw_parent_dir}")

    nights = []
    for item in parent.iterdir():
        if item.is_dir() and len(item.name) == 8 and item.name.isdigit():
            try:
                # Validate it's a real date
                parse_date(item.name)
                # Check if it has a raw subdirectory
                if (item / "raw").exists():
                    nights.append(item.name)
            except ValueError:
                # Not a valid date, skip
                pass

    return sorted(nights)


def write_nights_file(nights: list[str], output_file: str, comment: str = ""):
    """Write nights to output file with optional header comment."""
    with open(output_file, "w") as f:
        f.write("# Nights list for batch processing\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if comment:
            f.write(f"# {comment}\n")
        f.write(f"# Total nights: {len(nights)}\n")
        f.write("\n")

        for night in nights:
            f.write(f"{night}\n")

    print(f"✓ Wrote {len(nights)} nights to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate nights list file for batch processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate consecutive nights
  %(prog)s --start 20240625 --end 20240630 -o nights.txt

  # Generate specific nights
  %(prog)s --nights 20240625,20240627,20240629 -o nights.txt

  # Auto-discover from raw data directory
  %(prog)s --auto-discover -o nights.txt

  # Filter by month
  %(prog)s --start 20240601 --end 20240631 -o june_nights.txt
        """,
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--start",
        help="Start date (YYYYMMDD, use with --end)",
    )
    input_group.add_argument(
        "--nights",
        help="Comma-separated list of nights (YYYYMMDD,YYYYMMDD,...)",
    )
    input_group.add_argument(
        "--auto-discover",
        action="store_true",
        help="Auto-discover nights from RAW_PARENT_DIR (from .env)",
    )

    parser.add_argument(
        "--end",
        help="End date (YYYYMMDD, use with --start)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--comment",
        default="",
        help="Optional comment to include in output file header",
    )
    parser.add_argument(
        "--raw-parent-dir",
        help="Override RAW_PARENT_DIR from environment (for --auto-discover)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.start and not args.end:
        parser.error("--start requires --end")
    if args.end and not args.start:
        parser.error("--end requires --start")

    # Generate nights list
    try:
        if args.start and args.end:
            nights = generate_date_range(args.start, args.end)
            comment = args.comment or f"Date range: {args.start} to {args.end}"

        elif args.nights:
            nights = parse_nights_list(args.nights)
            comment = args.comment or "Specific nights"

        elif args.auto_discover:
            # Get RAW_PARENT_DIR from environment or argument
            raw_parent_dir = args.raw_parent_dir or os.getenv("RAW_PARENT_DIR")
            if not raw_parent_dir:
                print(
                    "ERROR: RAW_PARENT_DIR not set. Either:",
                    file=sys.stderr,
                )
                print("  1. Source .env file first", file=sys.stderr)
                print("  2. Use --raw-parent-dir argument", file=sys.stderr)
                sys.exit(1)

            nights = auto_discover_nights(raw_parent_dir)
            if not nights:
                print(
                    f"WARNING: No nights found in {raw_parent_dir}",
                    file=sys.stderr,
                )
                sys.exit(1)

            comment = args.comment or f"Auto-discovered from {raw_parent_dir}"
            print(f"Found {len(nights)} nights with raw data:")
            for night in nights:
                print(f"  {night}")
            print()

        # Write output
        write_nights_file(nights, args.output, comment)

        print("\nNext steps:")
        print(f"  1. Review: cat {args.output}")
        print(f"  2. Process: nickel run <config.yaml> with nights from {args.output}")

    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
