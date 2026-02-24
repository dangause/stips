#!/usr/bin/env python3
"""Split LSST log files by quantum/detector for parallel execution analysis.

When pipetask runs with parallel jobs (-j > 1), multiple workers write to the
same log file, interleaving entries from different quanta/detectors. This script
parses the dataId information from LSST long-log format and splits log entries
into separate files per detector, exposure, or quantum.

LSST log format includes dataId in parentheses:
    INFO 2026-02-12T09:23:21.221-08:00 lsst.pipe.base (cpBiasIsr:{instrument: 'Nickel', detector: 0, exposure: 86008005})(file.py:217) - Message

Usage:
    # Split by detector
    python split_log_by_quantum.py logs/RUN_ID/calibs/20230519.log \\
        --output-dir logs/RUN_ID/calibs/20230519_by_detector \\
        --split-by detector

    # Split by exposure
    python split_log_by_quantum.py logs/RUN_ID/science/20230519.log \\
        --output-dir logs/RUN_ID/science/20230519_by_exposure \\
        --split-by exposure

    # Split by detector+exposure combination
    python split_log_by_quantum.py logs/RUN_ID/science/20230519.log \\
        --output-dir logs/RUN_ID/science/20230519_by_quantum \\
        --split-by detector,exposure
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_data_id(line: str) -> dict[str, str] | None:
    """Extract dataId from LSST long-log format.

    LSST --long-log format includes dataId in parentheses:
        (cpBiasIsr:{instrument: 'Nickel', detector: 0, exposure: 86008005, band: 'clear', ...})

    Args:
        line: Log line

    Returns:
        Dictionary of dataId keys/values, or None if no dataId found
    """
    # Match dataId in parentheses: (taskLabel:{key: value, ...})
    match = re.search(r"\((\w+):\{([^}]+)\}\)", line)
    if not match:
        return None

    task_label = match.group(1)
    data_id_str = match.group(2)

    # Parse key-value pairs
    # Format: key: value, key: value, ...
    # Values can be strings ('foo'), numbers, or other types
    data_id = {"task_label": task_label}

    # Simple regex to extract key-value pairs
    # Handles: detector: 0, exposure: 86008005, band: 'clear'
    for match in re.finditer(r"(\w+):\s*('([^']*)'|(\d+)|(\w+))", data_id_str):
        key = match.group(1)
        # Value is either: quoted string (group 3), number (group 4), or word (group 5)
        value = match.group(3) or match.group(4) or match.group(5)
        data_id[key] = value

    return data_id


def parse_lsst_timestamp(line: str) -> datetime | None:
    """Extract timestamp from LSST long-log format.

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
            return datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
    return None


def split_log_file(
    input_path: Path,
    output_dir: Path,
    split_by: list[str],
) -> None:
    """Split log file by quantum identifiers.

    Args:
        input_path: Path to input log file
        output_dir: Directory to write split log files
        split_by: List of dataId keys to split by (e.g., ['detector'], ['detector', 'exposure'])
    """
    # Read all lines
    with open(input_path) as f:
        lines = f.readlines()

    # Group lines by dataId
    # Map from tuple of split_by values to list of lines
    grouped_lines: dict[tuple[str, ...], list[str]] = defaultdict(list)
    unknown_lines: list[str] = []

    current_key: tuple[str, ...] | None = None

    for line in lines:
        # Try to extract dataId from this line
        data_id = parse_data_id(line)

        if data_id:
            # Build key from split_by fields
            key_parts = []
            for field in split_by:
                value = data_id.get(field, "unknown")
                key_parts.append(f"{field}{value}")
            current_key = tuple(key_parts)

        # Add line to appropriate group
        if current_key:
            grouped_lines[current_key].append(line)
        else:
            # Lines before first dataId go to "unknown"
            unknown_lines.append(line)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write split files
    total_files = len(grouped_lines)
    if unknown_lines:
        total_files += 1

    print(
        f"Splitting {input_path.name} into {total_files} files by {', '.join(split_by)}"
    )

    for key, log_lines in sorted(grouped_lines.items()):
        # Build filename from key
        filename = "_".join(key) + ".log"
        output_path = output_dir / filename

        with open(output_path, "w") as f:
            f.writelines(log_lines)

        print(f"  ✓ {output_path.name}: {len(log_lines)} lines")

    # Write unknown lines if any
    if unknown_lines:
        unknown_path = output_dir / "unknown.log"
        with open(unknown_path, "w") as f:
            f.writelines(unknown_lines)
        print(f"  ✓ unknown.log: {len(unknown_lines)} lines (no dataId)")

    print(f"\n✓ Split complete: {output_dir}")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_log", type=Path, help="Path to input log file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write split log files",
    )
    parser.add_argument(
        "--split-by",
        default="detector",
        help='Comma-separated dataId keys to split by (default: "detector"). Examples: "detector", "exposure", "detector,exposure", "detector,band"',
    )

    args = parser.parse_args()

    if not args.input_log.exists():
        print(f"Error: File not found: {args.input_log}")
        return 1

    # Parse split_by argument
    split_by_list = [s.strip() for s in args.split_by.split(",")]

    try:
        split_log_file(args.input_log, args.output_dir, split_by_list)
        return 0
    except Exception as e:
        print(f"Error splitting log file: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
