#!/usr/bin/env python
"""
Gathers ingest statistics for a given date range.
"""
import argparse
import calendar
import datetime
import sys
from pathlib import Path

from lick_archive.authorization.override_access import OverrideAccessFile
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db import db_utils
from lick_archive.db.archive_schema import FileMetadata
from sqlalchemy import func, select

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

# Setup django before importing any django classes
from lick_archive.utils.django_utils import setup_django, setup_django_logging

setup_django()

from lick_archive.apps.archive_auth.models import DBOverrideAccessFile


def parse_day_arg(date_string):
    """Parse a date string in one of our accepted command line formats.

    Args:
        date_string (str):      The date string, in either MM/DD or ISO formats.

    Return:
        (:obj:`datetime.date`): The parsed date. If no year is given the current year is used.
    """
    current_year = datetime.date.today().year
    # See if it's a day without a year in US format
    try:
        dt = datetime.datetime.strptime(date_string, "%m/d%")
        start_date = datetime.date(year=current_year, month=dt.month, day=dt.day)
        return start_date
    except:
        # Try isoformat. We let this exception escape because if this fails,
        # it's an invalid argument
        start_date = datetime.date.fromisoformat(date_string)
        return start_date


def parse_date_arg(date_strings):
    """
    Parse the date argument to the script, which can be in multiple formats.

    Args:
        date_strings (list): A list of the command line dates given. This can have 1 or 2 entries.

    Return:
        (:obj:`datetime.date`): The starting date of the date range.
        (:obj:`datetime.date`): The ending date of the date range, which may be the same
                                           as the start date if it's a one day range.
    """
    # Get the date strings from the passed in array
    date_string1 = date_strings[0]

    if len(date_strings) > 1:
        date_string2 = date_strings[1]
    else:
        date_string2 = None

    start_date = None
    end_date = None

    # See if one of the allowed month formats (ie. "3" or "Mar" or "March")
    try:
        dt = datetime.datetime.strptime(date_string1, "%b")
    except:
        # Try the unabbrievated month
        try:
            dt = datetime.datetime.strptime(date_string1, "%B")
        except:
            dt = None

    if dt is not None:
        # Use the first day of the month in the current year as the start,
        # and the last day as the end.
        current_year = datetime.date.today().year
        start_date = datetime.date(year=current_year, month=dt.month, day=1)
        end_date = datetime.date(
            year=current_year,
            month=dt.month,
            day=calendar.monthrange(current_year, dt.month)[1],
        )
        return start_date, end_date
    else:
        # Otherwise it's one or two days.
        start_date = parse_day_arg(date_string1)
        if date_string2 is None:
            end_date = start_date
        else:
            end_date = parse_day_arg(date_string2)

        if end_date < start_date:
            raise ValueError("The end date must be after the start date")
        return start_date, end_date


def main():
    parser = argparse.ArgumentParser(
        description="Display ingest statistics for a given date."
    )
    parser.add_argument(
        "date",
        type=str,
        nargs="+",
        help="The date can be in the following formats.\n"
        "* By Month Number (1-12) or name.\n"
        "* By Day (MM/DD or (YYYY-MM-DD)\n"
        "* Day range: (YYYY-MM-DD YYYY-MM-DD)",
    )
    parser.add_argument(
        "-d",
        "--directory",
        default="/data/data/",
        type=str,
        help="The directory where the archive is mounted.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only display the ingest report, do not display status messages.",
    )
    args = parser.parse_args()

    # Setup django logging, but with minimum info
    setup_django_logging(Path.cwd() / "ingest_stats.log", "ERROR")

    try:

        start_date, end_date = parse_date_arg(args.date)

        archive_root = Path(args.directory)
        if not archive_root.is_dir():
            raise ValueError(
                f"The passed in directory {args.directory} does not exist or is not a directory."
            )

    except Exception as e:
        print(f"Invalid arguments: {e}", file=sys.stderr)
        parser.print_usage(sys.stderr)
        sys.exit(1)

    # Initialize databse connection
    db_engine = db_utils.create_db_engine()
    db_session = db_utils.open_db_session(db_engine)

    # First part of the count statement
    db_count_stmt = select(func.count(FileMetadata.id))

    # The sections counted for each day. There's one per instrument + the override.access
    # files
    instruments = lick_archive_config.ingest.supported_directories

    if not args.quiet:
        print(f"Scanning for files from {start_date} to {end_date}")

    # Loop over each day, populating results
    # results is keyed by date, then instrument to a list.
    # Example:
    #   { datetime.date(2023, 1, 1): { 'AO': [300, 299], 'shane': [0, 0] },
    #     datetime.date(2023, 1, 2): { 'AO': [2, 2], 'shane': [10, 10] } }
    # The first item in the list is the # of files found on the filesystem for that date
    # the second item is the # of files found in the databasse for that date
    results = dict()
    dt = start_date
    while dt <= end_date:

        # Default to 0 results
        results[dt] = {i: [0, 0] for i in instruments}

        for instr in instruments:
            # Construct the directory path for each instrument and get the counts
            directory = archive_root / dt.strftime("%Y-%m/%d") / instr
            if not args.quiet:
                print(
                    f"Scanning filesystem for files in {directory.relative_to(archive_root)}"
                )

            if directory.is_dir():
                file_count = 0
                for file in directory.iterdir():
                    if file.is_file():
                        if not OverrideAccessFile.check_filename(
                            file
                        ) and file.name.endswith(".access"):
                            # Some weird editor backup override.access files exist, skip those
                            continue
                        file_count += 1

                results[dt][instr][0] = file_count

            if not args.quiet:
                print(
                    f"Scanning database for files in {directory.relative_to(archive_root)}"
                )

            result = db_utils.execute_db_statement(
                db_session,
                db_count_stmt.where(FileMetadata.filename.like(str(directory) + "%")),
            )
            results[dt][instr][1] = (
                result.scalar()
                + DBOverrideAccessFile.objects.filter(
                    night=dt, instrument_dir=instr
                ).count()
            )
        dt += datetime.timedelta(days=1)

    # Now print a report.
    print(f"Ingest Report from {start_date.isoformat()} to {end_date.isoformat()}")
    report_fmt = f"{{:<10}} {{:<{len('Instrument')}}}  {{:>{len('Filesystem')}}}  {{:>{len('Database')}}}  {{:{len('Result')}}}"
    print(report_fmt.format("Date", "Instrument", "Filesystem", "Database", "Result"))
    for dt in sorted(results.keys()):
        for instr in instruments:
            # Compare the counts, using an uppercase MISMATCH to hopefully be a
            # value that stands out when skimming through the report
            if results[dt][instr][0] == results[dt][instr][1]:
                result = "ok"
            else:
                result = "MISMATCH"

            print(
                report_fmt.format(
                    dt.isoformat(),
                    instr,
                    results[dt][instr][0],
                    results[dt][instr][1],
                    result,
                )
            )


if __name__ == "__main__":
    sys.exit(main())
