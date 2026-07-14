#!/usr/bin/env python
"""
Resync file sizes in the metadata database.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.db_utils import BatchedDBOperation, create_db_engine
from lick_archive.utils.resync_utils import (
    ErrorList,
    SyncType,
    get_metadata_from_command_line,
)
from lick_archive.utils.script_utils import get_unique_file, setup_logging

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

logger = logging.getLogger(__name__)


def get_parser():
    """
    Parse bulk_ingest_metadata command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Resync file size metadata for Lick data in the archive database."
    )

    parser.add_argument(
        "archive_root", type=str, help="Top level directory of the archived Lick data."
    )
    parser.add_argument(
        "--date_range",
        type=str,
        help='Date range of files to ingest. Examples: "2010-01-04", "2010-01-01:2011-12-31". Defaults to all.',
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Number of rows to update in the database at once, defaults to 10,000",
    )
    parser.add_argument(
        "--instruments",
        type=str,
        nargs="+",
        help="Which instruments to resync from. Defaults to all.",
    )
    parser.add_argument(
        "--dry_run",
        default=False,
        action="store_true",
        help="Only display what needs to be updated, don't do the update",
    )
    parser.add_argument(
        "--ignore_mtime",
        default=False,
        action="store_true",
        help="Ignore mtime when resyncing files.",
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
    return parser


def main(args: argparse.Namespace) -> int:
    try:
        # Setup logging and an ingest_failures file.
        start_time = datetime.now(timezone.utc)
        setup_logging(args.log_path, "resync_date_range", args.log_level)

        error_file = get_unique_file(Path("."), "resync_failures", "txt")
        error_list = ErrorList(error_file)

        # Setup the database connection
        db_engine = create_db_engine(args.username, args.dbname)

        # Get the metadata specified on command line
        metadata = get_metadata_from_command_line(db_engine, args)

        if metadata is None:
            return 1

        # Update the file_size/mtime information in batches
        total = 0
        unchanged = 0
        needed_update = 0
        failed_to_read = 0
        with BatchedDBOperation(db_engine, args.batch_size) as batch:

            for file_metadata in metadata:
                file_path = Path(file_metadata.filename)
                total += 1
                try:
                    stat_info = (
                        file_path.lstat()
                        if file_path.is_symlink()
                        else file_path.stat()
                    )
                    filesize = stat_info.st_size
                    mtime = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)
                except Exception:
                    msg = f"Failed to stat {file_path}."
                    if not args.dry_run:
                        error_list.add_file(file_path, SyncType.UPDATE, msg)
                    logger.error(msg, exc_info=True)
                    continue

                needs_update = False

                if filesize != file_metadata.file_size:
                    needs_update = True
                    logger.info(
                        f"Updating {file_path} file size from {file_metadata.file_size} to {filesize} "
                    )
                    file_metadata.file_size = filesize

                if not args.ignore_mtime and mtime != file_metadata.mtime:
                    needs_update = True
                    logger.info(
                        f"Updating {file_path} mtime from {file_metadata.mtime} to {mtime} "
                    )
                    file_metadata.mtime = mtime

                if needs_update:
                    needed_update += 1
                    if not args.dry_run:
                        batch.update(file_metadata.id, file_metadata)
                else:
                    unchanged += 1

        logger.info(
            f"Of {total} files, {needed_update} are different and {unchanged} are unchanged."
        )
        logger.info(f"{failed_to_read} files failed to be read.")
        logger.info(
            f"Updated {batch.success} of {batch.total} changed files with {batch.total - batch.success} failures and {batch.success_retries} successful retries."
        )
        logger.info(f"Duration: {datetime.now(timezone.utc) - start_time}")

    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
