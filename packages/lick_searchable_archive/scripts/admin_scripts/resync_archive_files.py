#!/usr/bin/env python3
"""
Rsync files in the archive filesystem with the archive database.
"""

import argparse
import logging
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from lick_archive.db import db_utils

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging
from lick_archive.utils.script_utils import get_log_path, get_unique_file
from sqlalchemy import select

setup_django()

from lick_archive.apps.archive_auth.api import save_oaf_to_db
from lick_archive.authorization.override_access import OverrideAccessFile
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.db.db_utils import (
    BatchedDBOperation,
    create_db_engine,
    find_file_metadata,
)
from lick_archive.metadata.reader import read_file
from lick_archive.utils.resync_utils import ErrorList, SyncType, get_dirs_for_daterange

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

logger = logging.getLogger(__name__)


def get_parser():
    """
    Parse resync_date_range command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Ingest or update metadata for Lick data into the archive database.\n"
        "A log file of the ingest is created in resync_date_range_<timestamp>.log.\n"
        "A separate resync_failures.n.txt is also created listing files that failed ingesting or updating.\n"
        "By default updates will only be made to files with a different size or mtime from that in the"
        "database, but this can be changed with the --force option"
    )
    parser.add_argument(
        "--date_range",
        type=str,
        help='Date range of files to ingest, or "all" for everything. Examples: "2010-01-04", "2010-01-01:2011-12-31".',
    )
    parser.add_argument(
        "--dry_run",
        default=False,
        action="store_true",
        help="Run a dry run that does not do any updates but instead only logs what would have been updated.",
    )
    parser.add_argument("--files", type=Path, nargs="+", help="Files to resync.")
    parser.add_argument(
        "--instruments",
        type=str,
        default="all",
        nargs="*",
        help="Which instruments to get metadata from. Defaults to all.",
    )
    parser.add_argument(
        "--force",
        default=False,
        action="store_true",
        help="Force updates to always update existing files even if there's no change in the file size or mtime.",
    )
    parser.add_argument(
        "--archive_root",
        type=Path,
        help="Top level directory of the archived Lick data. If not given the value in the archive config file is used.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Number of rows to insert or update into the database at once, defaults to 10,000",
    )
    parser.add_argument(
        "-d",
        "--db_name",
        type=str,
        default="archive",
        help='Name of the database to connect to. Defaults to "archive".',
    )
    parser.add_argument(
        "-U",
        "--db_user",
        type=str,
        default="archive",
        help='Name of the database user to connect with. Defaults ot "archive".',
    )
    parser.add_argument(
        "--log_path",
        "-l",
        type=str,
        help="Directory to write log file to. Defaults to the current directory.",
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


def main(args):

    try:
        # Setup logging and an ingest_failures file.
        start_time = datetime.now(timezone.utc)
        logfile = get_log_path("resync_archive_files", args.log_path)
        setup_django_logging(logfile, args.log_level, stdout_level="INFO")

        error_file = get_unique_file(Path("."), "resync_failures", "txt")
        error_list = ErrorList(error_file)

        # Setup database connection
        db_engine = create_db_engine(database=args.db_name, user=args.db_user)

        # Start resyncing files in batches
        with BatchedDBOperation(db_engine, args.batch_size) as db_batch:

            if args.date_range is not None:
                # Process files on a directory by directory basis from the date range given
                logger.info(f"Resyncing : {args.date_range} : {args.instruments}")

                for dir in get_dirs_for_daterange(args.date_range, args.instruments):
                    resync_files(args, db_batch, error_list, dir.iterdir())

            elif args.files is not None:
                # Check that the given files exist

                for file in args.files:
                    if not file.exists() or not file.is_file():
                        logger.error(f"File {file} does not exist or is not a file")
                        return 1

                logger.info(f"Resyncing : {len(args.files)} files")
                resync_files(args, db_batch, error_list, args.files)
            else:
                logger.error("Must specify one of --date_range or --files.")
                return 1

        error_list.add_batch_failures(db_batch.failures)

        logger.info(
            f"Synced {db_batch.success} of {db_batch.total} files, {db_batch.total - db_batch.success} failures and {db_batch.success_retries} successful retries."
        )
        logger.info(f"Duration: {datetime.now(timezone.utc) - start_time}")
    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1
    return 0


def resync_files(
    args, db_batch: BatchedDBOperation, error_list: ErrorList, files_to_resync: Iterator
):

    # Separate out override access files from other files
    oafs = []
    other_files = []

    for file_to_resync in files_to_resync:
        if OverrideAccessFile.check_filename(file_to_resync):
            try:
                oafs.append(OverrideAccessFile.from_file(file_to_resync))
            except Exception as e:
                error_list.add_file(file_to_resync, SyncType.OVERRIDE_FILE, str(e))
                logger.error(f"Failed to parse override access file: {e}")
                continue
        else:
            other_files.append(file_to_resync)

    # Update the override access files first
    for oaf in oafs:
        try:
            logger.info(f"Saving override access file: {oaf}")
            if not args.dry_run:
                save_oaf_to_db(oaf)
        except Exception as e:
            error_list.add_file(str(oaf), SyncType.OVERRIDE_FILE, str(e))
            logger.error(f"Failed to save {oaf} {e}", exc_info=True)
            continue

    # Resync the remaining files
    for file_to_resync in other_files:

        # See if this is an insert or update
        with closing(db_utils.open_db_session(db_batch.engine)) as session:
            file_metadata = find_file_metadata(
                session,
                select(FileMetadata).where(
                    FileMetadata.filename == str(file_to_resync)
                ),
            )

        if file_metadata is None:
            sync_type = SyncType.INSERT
            logger.info(f"New file {file_to_resync} discovered.")
        else:
            # See if the update can be skipped
            if not args.force:
                st_info = (
                    file_to_resync.lstat()
                    if file_to_resync.is_symlink()
                    else file_to_resync.stat()
                )
                mtime = datetime.fromtimestamp(st_info.st_mtime, tz=timezone.utc)
                if (
                    st_info.st_size == file_metadata.file_size
                    and mtime == file_metadata.mtime
                ):
                    continue
                else:
                    if st_info.st_size != file_metadata.file_size:
                        logger.info(
                            f"File {file_metadata.filename} has differing file_size. Current: {st_info.st_size} DB: {file_metadata.file_size}"
                        )
                    if mtime != file_metadata.mtime:
                        logger.info(
                            f"File {file_metadata.filename} has differing mtime. Current: {mtime} DB: {file_metadata.mtime}"
                        )
            sync_type = SyncType.UPDATE

        # Get the new metadata from the file
        try:
            new_file_metadata = read_file(file_to_resync)
        except Exception:
            msg = f"Failed reading metadata from new file {file_to_resync}"
            error_list.add_file(file_to_resync, sync_type, msg)
            logger.error(msg, exc_info=True)
            continue

        if sync_type == SyncType.INSERT:
            if not args.dry_run:
                db_batch.insert(new_file_metadata)
        else:
            if not args.dry_run:
                db_batch.update(
                    file_metadata.id, new_file_metadata, new_file_metadata.user_access
                )


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
