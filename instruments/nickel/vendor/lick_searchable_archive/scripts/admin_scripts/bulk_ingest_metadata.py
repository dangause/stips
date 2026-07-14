"""
Ingest metadata from existing data in the Lick archive in bulk.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from lick_archive.db.db_utils import (
    create_db_engine,
    insert_batch,
    insert_one,
    open_db_session,
)
from lick_archive.metadata.reader import read_file
from lick_archive.utils.script_utils import (
    get_files_for_daterange,
    get_unique_file,
    parse_date_range,
    setup_logging,
)

logger = logging.getLogger(__name__)


def get_parser():
    """
    Parse bulk_ingest_metadata command line arguments with argparse.
    """
    parser = argparse.ArgumentParser(
        description="Ingest metadata for Lick data into the archive database.\n"
        "A log file of the ingest is created in bulk_ingest_<timestamp>.log.\n"
        "A separate ingest_failures.n.txt is also created listing files that failed ingesting."
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
        help="Number of rows to insert into the database at once, defaults to 10,000",
    )
    parser.add_argument(
        "--instruments",
        type=str,
        nargs="+",
        help="Which instruments to get metadata from. Defaults to all.",
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


def retry_one_by_one(error_file, engine, batch):
    """
    Retry inserting a batch of metadata one row at a time, in case
    one of the rows failed due to a schema issue rather than an intermittent db issue.
    """
    for row in batch:
        try:
            insert_one(engine, row)
        except Exception as e:
            with open(error_file, "a") as f:
                print(f"Failed to retry {row.filename}: {e}", file=f)
            logger.error(f"Failed to retry {row.filename}: {e}")


def main(args):

    start_time = datetime.now(timezone.utc)

    # Setup database, logging, and an ingest_failures file.
    setup_logging(args.log_path, "bulk_ingest", args.log_level)
    logger.info(f"Bulk Started Ingest on {args.archive_root}")

    try:
        engine = create_db_engine()
        error_file = get_unique_file(Path("."), "ingest_failures", "txt")
        supported_instruments = ["shane", "AO"]
        (start_date, end_date) = parse_date_range(args.date_range)
        if args.instruments is not None:
            for instrument in args.instruments:
                if instrument not in supported_instruments:
                    logger.error(
                        f"{instrument} is not a supported instrument. It should be one of: {','.join(supported_instruments)}."
                    )
                    return 1
        else:
            args.instruments = supported_instruments

        # Get the files to read metadata from
        files = get_files_for_daterange(
            args.archive_root, start_date, end_date, args.instruments
        )

        # Insert metadata for the specified files in batches
        batch = []
        for file in files:
            try:
                logger.debug(f"Reading metadata from {file}.")
                next_row = read_file(file)
            except Exception as e:
                with open(error_file, "a") as f:
                    print(f"Failed to read {file}: {e}", file=f)
                logger.error(f"Failed to read {file}.", exc_info=True)
                continue

            logger.info(f"Finished reading metadata from {file}")
            batch.append(next_row)

            # Insert the batch once it's full
            if len(batch) >= args.batch_size:
                try:
                    session = open_db_session(engine)
                    insert_batch(session, batch)
                except Exception:
                    retry_one_by_one(error_file, engine, batch)
                batch = []
        # Insert any left over data that did not fill an entire batch
        if len(batch) > 0:
            try:
                session = open_db_session(engine)
                insert_batch(session, batch)
            except Exception:
                retry_one_by_one(error_file, engine, batch)
    except Exception:
        logging.error("Caught exception at end of main.", exc_info=True)
        return 1
    logger.info(
        f"Bulk Ingest Finished, total time {datetime.now(timezone.utc) - start_time}."
    )


if __name__ == "__main__":
    parser = get_parser()
    args = parser.parse_args()
    sys.exit(main(args))
