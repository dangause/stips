#!/usr/bin/env python
"""Reingest metadata for archive files using their header data."""
import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from lick_archive.db.archive_schema import FileMetadata
from lick_archive.metadata.data_dictionary import IngestFlags

# Setup django before importing any django files
from lick_archive.utils.django_utils import setup_django, setup_django_logging

setup_django()

from lick_archive import resync_utils
from lick_archive.db.db_utils import BatchedDBOperation, create_db_engine
from lick_archive.metadata.metadata_utils import get_hdul_from_string
from lick_archive.metadata.reader import read_hdul
from lick_archive.utils.script_utils import get_log_path, get_unique_file


def get_parser():
    """
    Parse command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Re-ingest metadata for files using the header data already in the database."
    )

    parser.add_argument(
        "--id_file",
        type=Path,
        help="A file containing database ids separated by whitespace.",
    )
    parser.add_argument("--ids", type=str, help="A list of database ids.")
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
        logfile = get_log_path("reingest_from_header", args.log_path)
        setup_django_logging(logfile, args.log_level, stdout_level="INFO")

        error_file = get_unique_file(Path("."), "resync_failures", "txt")
        error_list = resync_utils.ErrorList(error_file)

        # Setup the database connection
        db_engine = create_db_engine(args.db_user, args.db_name)

        # Get the metadata specified on command line
        metadata = resync_utils.get_metadata_from_command_line(db_engine, args)

        if metadata is None:
            return 1

        # Update the file metadata in batches
        with BatchedDBOperation(db_engine, args.batch_size) as batch:

            for file_metadata in metadata:
                try:
                    new_metadata = regen_metadata_from_header(file_metadata)
                except Exception:
                    msg = f"Failed to regenerate auth metadata for file {file_metadata.filename}"
                    logger.error(msg, exc_info=True)
                    error_list.add_file(
                        file_metadata.filename, resync_utils.SyncType.HEADER_UPDATE, msg
                    )
                    continue

                batch.update(file_metadata.id, new_metadata, new_metadata.user_access)

        logger.info(
            f"Updated {batch.success} of {batch.total} files with {batch.total - batch.success} failures and {batch.success_retries} successful retries."
        )
        logger.info(f"Duration: {datetime.now(timezone.utc) - start_time}")
    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1

    return 0


def regen_metadata_from_header(metadata: FileMetadata) -> FileMetadata:
    """Regenerate file metadata using the header information stored in the existing row.

    Args:
        metadata : The existing row of metadata for the file.

    Return:
        new_metadata: The new metadata regenerated from the header.
    """
    hdul = get_hdul_from_string([metadata.header])

    ingest_flags = IngestFlags(int(metadata.ingest_flags, 2))
    # Turn off flags not related to opening the fits file, so they can be reset by the re-reading of the header
    ingest_flags &= (
        IngestFlags.NO_FITS_END_CARD
        | IngestFlags.NO_FITS_SIMPLE_CARD
        | IngestFlags.FITS_VERIFY_ERROR
        | IngestFlags.INVALID_CHAR
    )

    new_metadata = read_hdul(metadata.filename, hdul, ingest_flags)

    # Make sure the new metadata object knows it's id
    new_metadata.id = metadata.id

    # Set file properties that aren't in the header
    new_metadata.file_size = metadata.file_size
    new_metadata.mtime = metadata.mtime
    return new_metadata


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
