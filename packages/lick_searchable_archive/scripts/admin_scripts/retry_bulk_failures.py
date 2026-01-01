"""
Retry failures from bulk_ingest_metadata.
"""

import argparse
import logging
import sys
from pathlib import Path

from lick_archive.db.archive_schema import FileMetadata
from lick_archive.db.db_utils import check_exists, create_db_engine, insert_one
from lick_archive.metadata.reader import read_file
from lick_archive.utils.script_utils import get_unique_file, setup_logging

logger = logging.getLogger(__name__)


def retry_one_file(error_file, failed_file):

    try:
        logger.info(f"Reading metadata from {failed_file}.")
        row = read_file(failed_file)
        logger.info(f"Finished reading metadata from {failed_file}.")
    except Exception as e:
        with open(error_file, "a") as f:
            print(f"Failed to retry {failed_file}: {e}", file=f)
        logger.error(f"Failed to retry {failed_file}.", exc_info=True)
        return

    try:
        logger.info(f"Inserting data for {failed_file}.")
        engine = create_db_engine()

        if not check_exists(
            engine, FileMetadata.id, FileMetadata.filename == row.filename
        ):
            insert_one(engine, row)
            logger.info(f"Finished inserting data for {failed_file}.")
        else:
            logger.info(f"{failed_file} already exists.")
    except Exception as e:
        with open(error_file, "a") as f:
            print(f"Failed to retry {failed_file}: {e}", file=f)
        logger.error(f"Failed to retry {failed_file}.", exc_info=True)


def main():
    parser = argparse.ArgumentParser(
        description='Retry failed files from an "ingest_failures" file created by bulk_metadata_ingest.\n'
        "A log file of the ingest is created in bulk_ingest_<timestamp>.log.\n"
        "A new ingest_failures.n.txt will be created for any files that still fail."
    )
    parser.add_argument(
        "ingest_failures",
        type=str,
        help='An ingest failures file from bulk metadata retry. Usually named "ingest_failures.n.txt".',
    )
    parser.add_argument(
        "-d",
        "--dbname",
        type=str,
        default="archive",
        help='Name of the database to connect to. Defaults to "archive".',
    )
    parser.add_argument(
        "-U",
        "--username",
        type=str,
        default="archive",
        help='Name of the database user to connect with. Defaults ot "archive".',
    )
    parser.add_argument(
        "--log_path", "-l", type=str, help="Directory to write log file to."
    )
    parser.add_argument(
        "--log_level",
        "-L",
        type=str,
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        default="DEBUG",
        help="Logging level to use.",
    )

    args = parser.parse_args()

    setup_logging(args.log_path, "retry_bulk_ingest", args.log_level)

    error_file = get_unique_file(Path("."), "ingest_failures", "txt")
    logger.info(f"Reading {args.ingest_failures}...")
    try:
        with open(args.ingest_failures, "r") as failures:
            for line in failures:
                if line.startswith("Failed to read") or line.startswith(
                    "Failed to retry"
                ):
                    parts = line.split()
                    failed_file = parts[3].rstrip(":")
                else:
                    continue

                retry_one_file(error_file, Path(failed_file))

    except Exception as e:
        with open(error_file, "a") as f:
            print(f"Failed to read {args.ingest_failures}: {e}", file=f)
        logger.error(f"Failed to read {args.ingest_failures}.", exc_info=True)


if __name__ == "__main__":
    sys.exit(main())
