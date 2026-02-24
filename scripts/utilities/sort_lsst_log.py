#!/usr/bin/env python3
"""Sort LSST log files by timestamp.

When pipetask runs with parallel jobs (-j > 1), multiple workers may write
to the same log file simultaneously, causing log entries to be slightly
out of chronological order. This script sorts log entries by their timestamps.

Usage:
    python sort_lsst_log.py input.log output.log
    python sort_lsst_log.py input.log  # overwrites input.log
"""

import re
import sys
from datetime import datetime
from pathlib import Path


def parse_lsst_timestamp(line: str) -> datetime | None:
    """Extract timestamp from LSST long-log format.

    LSST --long-log format:
        INFO 2026-02-12T09:10:59.344-08:00 lsst.ingest ()(ingest.py:994) - Message

    Args:
        line: Log line

    Returns:
        datetime object if timestamp found, None otherwise
    """
    # Match ISO 8601 timestamp with timezone
    match = re.match(
        r"^\w+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2})\s+", line
    )
    if match:
        timestamp_str = match.group(1)
        try:
            # Parse ISO 8601 with timezone
            # Python 3.7+ can handle this directly
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
    return None


def sort_log_file(input_path: Path, output_path: Path | None = None) -> None:
    """Sort log file by timestamps.

    Args:
        input_path: Path to input log file
        output_path: Path to output log file (default: overwrite input)
    """
    if output_path is None:
        output_path = input_path

    # Read all lines
    with open(input_path) as f:
        lines = f.readlines()

    # Group lines into entries (lines with timestamps + continuation lines)
    entries: list[tuple[datetime | None, list[str]]] = []
    current_timestamp = None
    current_lines: list[str] = []

    for line in lines:
        timestamp = parse_lsst_timestamp(line)
        if timestamp is not None:
            # New timestamped entry - save previous entry
            if current_lines:
                entries.append((current_timestamp, current_lines))
            current_timestamp = timestamp
            current_lines = [line]
        else:
            # Continuation line (no timestamp) - add to current entry
            current_lines.append(line)

    # Don't forget the last entry
    if current_lines:
        entries.append((current_timestamp, current_lines))

    # Sort entries by timestamp (None timestamps go to beginning)
    entries.sort(key=lambda x: x[0] or datetime.min)

    # Write sorted entries
    with open(output_path, "w") as f:
        for _, entry_lines in entries:
            f.writelines(entry_lines)

    print(f"Sorted {len(entries)} log entries")
    if output_path == input_path:
        print(f"Overwrote: {input_path}")
    else:
        print(f"Wrote to: {output_path}")


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    try:
        sort_log_file(input_path, output_path)
        return 0
    except Exception as e:
        print(f"Error sorting log file: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
