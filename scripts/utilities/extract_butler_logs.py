#!/usr/bin/env python3
"""Extract per-quantum log files from Butler repository.

LSST stores log messages issued during quantum execution as `tasklabel_log`
dataset types in the Butler repository. This script extracts these logs and
organizes them by detector/quantum for easier debugging of parallel runs.

Usage:
    python extract_butler_logs.py /path/to/repo \\
        --collection "Nickel/runs/20230519/calibs/*" \\
        --output-dir logs/20230519_from_butler/calibs

    python extract_butler_logs.py /path/to/repo \\
        --collection "Nickel/runs/20230519/science/*" \\
        --task-label isr \\
        --output-dir logs/20230519_from_butler/science
"""

import argparse
import sys
from pathlib import Path

from lsst.daf.butler import Butler


def extract_logs(
    repo: str,
    collection: str,
    output_dir: Path,
    task_label: str | None = None,
) -> None:
    """Extract quantum logs from Butler repository.

    Args:
        repo: Path to Butler repository
        collection: Collection pattern to search (e.g., "Nickel/runs/*/calibs/*")
        output_dir: Directory to write extracted log files
        task_label: Optional task label to filter (e.g., "isr", "cpBiasIsr")
    """
    butler = Butler(repo, collections=collection)

    # Find all log dataset types in the collection
    log_dataset_types = []
    for dataset_type in butler.registry.queryDatasetTypes():
        if dataset_type.name.endswith("_log"):
            if task_label is None or dataset_type.name.startswith(task_label):
                log_dataset_types.append(dataset_type.name)

    if not log_dataset_types:
        print(f"No log dataset types found in {collection}")
        if task_label:
            print(f"(filtered by task_label={task_label})")
        return

    print(f"Found {len(log_dataset_types)} log dataset types:")
    for dt in sorted(log_dataset_types):
        print(f"  - {dt}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract logs for each dataset type
    total_logs = 0
    for dataset_type_name in sorted(log_dataset_types):
        # Query all log datasets for this type
        refs = list(
            butler.registry.queryDatasets(dataset_type_name, collections=collection)
        )

        if not refs:
            print(f"\n{dataset_type_name}: No logs found")
            continue

        print(f"\n{dataset_type_name}: {len(refs)} log files")

        # Create subdirectory for this task
        task_dir = output_dir / dataset_type_name.replace("_log", "")
        task_dir.mkdir(parents=True, exist_ok=True)

        # Extract each log file
        for ref in refs:
            # Get the dataId for filename
            data_id = ref.dataId

            # Build filename from dataId
            parts = []
            if "detector" in data_id.dimensions.names:
                parts.append(f"det{data_id['detector']}")
            if "exposure" in data_id.dimensions.names:
                parts.append(f"exp{data_id['exposure']}")
            if "day_obs" in data_id.dimensions.names:
                parts.append(f"day{data_id['day_obs']}")
            if "band" in data_id.dimensions.names:
                parts.append(f"band{data_id['band']}")

            filename = "_".join(parts) if parts else "log"
            log_path = task_dir / f"{filename}.log"

            # Retrieve log content
            try:
                log_obj = butler.get(ref)
                # Log dataset is a ButlerLogRecords object
                # Convert to text
                if hasattr(log_obj, "text"):
                    log_text = log_obj.text
                elif hasattr(log_obj, "content"):
                    log_text = log_obj.content
                else:
                    # Try to get string representation
                    log_text = str(log_obj)

                # Write to file
                with open(log_path, "w") as f:
                    f.write(log_text)

                total_logs += 1
                print(f"  ✓ {log_path}")

            except Exception as e:
                print(f"  ✗ Failed to extract {ref}: {e}")

    print(f"\n✓ Extracted {total_logs} log files to {output_dir}")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repo", help="Path to Butler repository")
    parser.add_argument(
        "--collection",
        required=True,
        help='Collection pattern (e.g., "Nickel/runs/20230519/calibs/*")',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write extracted log files",
    )
    parser.add_argument(
        "--task-label",
        help="Optional task label to filter (e.g., 'isr', 'cpBiasIsr')",
    )

    args = parser.parse_args()

    try:
        extract_logs(
            repo=args.repo,
            collection=args.collection,
            output_dir=args.output_dir,
            task_label=args.task_label,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
