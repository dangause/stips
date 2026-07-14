#!/usr/bin/env python
"""Reingest metadata for archive files using their header data."""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


from lick_archive.db.db_utils import BatchedDBOperation, create_db_engine

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging
from lick_archive.utils.script_utils import get_log_path, get_unique_file

setup_django()


from lick_archive.apps.archive_auth.api import save_oaf_to_db
from lick_archive.authorization import user_access
from lick_archive.authorization.override_access import OverrideAccessFile
from lick_archive.utils.resync_utils import (
    ErrorList,
    SyncType,
    get_metadata_from_command_line,
)


def get_parser():
    """
    Parse command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Re-evaluate the authoriztion of files and re-ingest any override access files."
    )

    parser.add_argument(
        "--id_file",
        type=Path,
        help="A file containing database ids separated by whitespace.",
    )
    parser.add_argument("--ids", nargs="+", type=int, help="A list of database ids.")
    parser.add_argument("--files", type=str, nargs="+", help="A list of filenames.")
    parser.add_argument(
        "--date_range",
        type=str,
        help='Date range of files to ingest. Examples: "2010-01-04", "2010-01-01:2011-12-31". Defaults to all.',
    )
    parser.add_argument(
        "--instruments",
        type=str,
        default="all",
        nargs="*",
        help="Which instruments to get metadata from. Defaults to all.",
    )

    parser.add_argument(
        "--db_name",
        default="archive",
        type=str,
        help='Name of the database to update. Defaults to "archive"',
    )
    parser.add_argument(
        "--db_user",
        default="archive",
        type=str,
        help='Name of the database user. Defaults to "archive"',
    )
    parser.add_argument(
        "--override_only",
        default=False,
        action="store_true",
        help="Only sync override.access files in the given daterange.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Number of rows to update in the database at once, defaults to 10,000",
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


def main(args):

    try:
        # Setup logging and an ingest_failures file.
        start_time = datetime.now(timezone.utc)
        log_path = get_log_path("resync_auth")
        setup_django_logging(log_path, args.log_level, stdout_level="INFO")
        error_file = get_unique_file(Path("."), "resync_failures", "txt")
        error_list = ErrorList(error_file)

        # Resync any override access files
        total_oaf = 0
        successful_oaf = 0
        synced_oaf_paths = set()

        if not args.override_only:
            # Setup the database connection
            db_engine = create_db_engine(args.db_user, args.db_name)

            # Get the metadata specified on command line
            metadata = get_metadata_from_command_line(db_engine, args)

            if metadata is None:
                return 1

            # Update the auth information in batches
            with BatchedDBOperation(db_engine, args.batch_size) as batch:
                for file_metadata in metadata:
                    if file_metadata is None:
                        # One of the datasets could not be found
                        continue
                    else:
                        logger.info(f"Processing metadata {file_metadata.id}")
                    # Make sure all override access files in a path have been synced before
                    # re-running the authorization code on any files in it
                    file_path = Path(file_metadata.filename).parent
                    if file_path not in synced_oaf_paths:
                        total, success = resync_override_access_files(
                            args, file_path, error_list
                        )
                        total_oaf += total
                        successful_oaf += success
                        synced_oaf_paths.add(file_path)

                    # Re-generate auth metadata
                    try:
                        new_metadata = user_access.set_auth_metadata(file_metadata)
                    except Exception:
                        msg = f"Failed to regenerate auth metadata for file {file_metadata.filename}"
                        logger.error(msg, exc_info=True)
                        error_list.add_file(file_metadata.filename)
                        continue
                    batch.update(
                        file_metadata.id, new_metadata, new_metadata.user_access
                    )

        logger.info(
            f"Updated {batch.success} of {batch.total} files with {batch.total - batch.success} failures and {batch.success_retries} successful retries."
        )
        logger.info(
            f"Updated {successful_oaf} of {total_oaf} override access files with {total_oaf - successful_oaf} failures."
        )
        logger.info(f"Duration: {datetime.now(timezone.utc) - start_time}")

    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1

    return 0


def resync_override_access_files(
    args: argparse.Namespace, file_path: Path, error_list: ErrorList
):
    logger.info(
        f"Resyncing Override Access Files: {args.date_range} : {args.instruments}"
    )
    total = 0
    successful = 0
    for file in file_path.iterdir():
        if OverrideAccessFile.check_filename(file):
            total += 1
            try:
                access_file = OverrideAccessFile.from_file(file)
            except ValueError as e:
                logging.error(f"Invalid override access file {file} in dir {dir}: {e}")
                error_list.add_file(file, SyncType.OVERRIDE_FILE, str(e))
                continue
            try:
                save_oaf_to_db(access_file)
                successful += 1
            except Exception as e:
                msg = f"Failed to save {access_file} to db: {e.__class__.__name__}: {e}"
                error_list.add_file(file, SyncType.OVERRIDE_FILE, msg)
                logging.error(msg, exc_info=True)
    return total, successful


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
