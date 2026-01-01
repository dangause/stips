"""Utility functions specific to the command line scripts used to resync the archive metadata database."""

import argparse
import enum
import logging
import re
from collections.abc import Iterator
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db import db_utils
from lick_archive.db.archive_schema import FileMetadata
from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class SyncType(enum.Enum):
    """The type of sync operation that failed."""

    INSERT = "insert"
    """Inserting new metadata into the archive."""

    HEADER_UPDATE = "header update"
    """Updating existing metadata using existing header information in db."""

    UPDATE = "update"
    """Updating existing metdadata using the original file."""

    OVERRIDE_FILE = "override access file"
    """Adding/updating an override access file"""


class ErrorList:
    """Clas to keep track of failures ingesting or updating metadata in the archive in a consistent format that
    can be easilly retried.

    Args:
        error_file : Name of the file to write failures to.
    """

    def __init__(self, error_file: str | Path):
        self.error_file = error_file

    def add_file(self, filename: str | Path, sync_type: SyncType, msg: str):
        """Add a failure record for a single file.

        Args:
            filename:  The name of the file that failed.
            sync_type: The type of operation on filename that failed.
            msg:       A message describing the failure.
        """
        with open(self.error_file, "a") as f:
            print(f"{filename}|{sync_type.value}|{msg}", file=f)

    def add_batch_failures(self, failures: list[tuple[str | Path, str, str]]):
        """Add multiple failure records from a BatchedDBOperation

        Arg:
            failures: A list of tuples containing the filename, sync_type, and msg
                      as described to the args to :method:`ErrorList.add_file`.
        """
        with open(self.error_file, "a") as f:
            for filename, sync_type, msg in failures:
                print(f"{filename}|{sync_type}|{msg}", file=f)


def get_metadata_from_command_line(
    db_engine: Engine, args: argparse.Namespace
) -> None | Iterator[FileMetadata | None]:
    """Get database metadata using the conventions for resync script command line arguments.

        - `--date_range`  A date range (see :function:`parse_date_range`)
        - `--instruments` A list of instrument directory names to look for. Must be specified
                          if `--date_range` is given.
        - `--files`       A list of filenames
        - `--id_file`     A file containing database ids separated by whitespace
        - `--ids`         A list of database ids

    Args:
        db_engine: The database engine to use when querying
        args:      The :class:`argparse.ArgumentParser` results from parsing the command line

    Return: None if the command line arguments were not found, otherwise an iterator
            of metadata for each file or id matching the arguments.
            If one of the passed in filenames of ids could not be found in the database,
            None will be returned for that item instead.
    """
    # Get the metadata using a date range specified on command line
    if args.date_range is not None:
        # Get metadata from files in the archive file system
        metadata = get_metadata_from_date_range(
            db_engine, args.date_range, args.instruments
        )

    # Get the metadata using file names specified on command line
    elif args.files is not None and len(args.files) > 0:
        if isinstance(args.files, str) or isinstance(args.files, Path):
            args.files = [args.files]

        metadata = get_metadata_from_files(db_engine, args.files)

    # Get the metadata from a file containing database ids
    elif args.id_file is not None:
        id_list = read_id_file(args.id_file)
        metadata = get_metadata_from_ids(db_engine, id_list)

    # Get the metadata using a list of database ids
    elif args.ids is not None and len(args.ids) > 0:
        if isinstance(args.ids, str):
            args.ids = [args.ids]
        metadata = get_metadata_from_ids(db_engine, args.ids)
    else:
        logger.error("Must specify one of --date_range, --files, --id_file, or --ids.")
        metadata = None

    return metadata


def get_metadata_from_files(
    db_engine: Engine, files: list[str | Path]
) -> Iterator[FileMetadata | None]:
    """Query the database for metadata from a list of filenames.

    Args:
        db_engine: The database engine to use.
        files: The list of filenames to query for

    Return: An iterator returning the metadata for each file in files, or None of the file could not be found.
    """
    with db_utils.open_db_session(db_engine) as session:
        for file in files:
            yield db_utils.find_file_metadata(
                session,
                select(FileMetadata)
                .options(selectinload(FileMetadata.user_access))
                .where(FileMetadata.filename == str(file)),
            )


def get_metadata_from_ids(
    db_engine: Engine, ids: list[int]
) -> Iterator[FileMetadata | None]:
    """Query the database for metadata from a list of ids.

    Args:
        db_engine: The database engine to use.
        ids: The list of filenames to query for

    Return: An iterator returning the metadata for each id, or None of the id could not be found.
    """
    with db_utils.open_db_session(db_engine) as session:
        for id in ids:
            yield db_utils.find_file_metadata(
                session,
                select(FileMetadata)
                .options(selectinload(FileMetadata.user_access))
                .where(FileMetadata.id == id),
            )


def get_metadata_from_date_range(
    db_engine: Engine, date_range: str, instruments: list[str]
) -> Iterator[FileMetadata]:
    archive_root = lick_archive_config.ingest.archive_root_dir
    instrument_dirs = get_valid_instrument_dirs(instruments)
    start_date, end_date = parse_date_range(date_range)

    current_date = start_date
    while current_date <= end_date:
        for instr_dir in instrument_dirs:
            dir_to_query = str(
                archive_root / current_date.strftime("%Y-%m/%d") / instr_dir / "%"
            )
            logger.debug(f"Querying: {dir_to_query}")
            with closing(db_utils.open_db_session(db_engine)) as session:
                results = list(
                    db_utils.execute_db_statement(
                        session,
                        select(FileMetadata)
                        .options(selectinload(FileMetadata.user_access))
                        .where(FileMetadata.filename.like(dir_to_query)),
                    ).scalars()
                )
            for result in results:
                yield result
        current_date += timedelta(days=1)


def get_valid_instrument_dirs(instrument_dirs: list[str]) -> list[str]:
    """Validate a list of instrument subdirectory names from the command line.

    Args:
        instrument_dirs: Instrument directory names from the command line. These are considered
                         valid if they exist in the archive configuration under
                         :attribute:`LickArchiveConfigFile.ingest.supported_directories`. An empty list
                         of the value of "all" is replaced by all supported_directories.

    Return: A list of the validated instrument directories.

    """
    if instrument_dirs is None or len(instrument_dirs) == 0 or "all" in instrument_dirs:
        # Use all supported directories
        instrument_dirs = lick_archive_config.ingest.supported_directories
    else:
        # Validate the instruments
        for instr_dir in instrument_dirs:
            if instr_dir not in lick_archive_config.ingest.supported_directories:
                raise ValueError(
                    f"Instrument dir {instr_dir} is not in the list of supported instrument directories: {','.join(lick_archive_config.ingest.supported_directories)}"
                )

    return instrument_dirs


def parse_date_range(date_range):
    """
    Parse a date range from the command line. The date range's format is "YYYY-MM-DD" indicating a single day or
    "YYYY-MM-DD:YYYY-MM-DD" indicating a range.

    Returns:
    start_date: A datetime.date of the start of the date range.
    end_date: A datetime.date of the end of the date range.
    """
    if date_range is not None:
        if ":" in date_range:
            (start_str, end_str) = date_range.split(":")
        else:
            start_str = date_range
            end_str = None

        date_list = start_str.split("-")
        if len(date_list) < 3:
            raise ValueError(
                f"'{start_str}' is an invalid start date. It should be YYYY-MM-DD."
            )

        try:
            start_date = date(int(date_list[0]), int(date_list[1]), int(date_list[2]))
        except:
            raise ValueError(
                f"'{start_str}' is an invalid start date. It should be YYYY-MM-DD."
            )

        if end_str is None:
            end_date = start_date
        else:
            date_list = end_str.split("-")
            if len(date_list) < 3:
                raise ValueError(
                    f"'{end_str}' is an invalid end date. It should be YYYY-MM-DD."
                )

            try:
                end_date = date(int(date_list[0]), int(date_list[1]), int(date_list[2]))
            except:
                raise ValueError(
                    f"'{end_str}' is an invalid start date. It should be YYYY-MM-DD."
                )

        return (start_date, end_date)
    return (None, None)


def get_dirs_for_daterange(date_range, instrument_dirs):
    """
    Scan the lick archive root dir for files that match command line parameters.

    The direcotires in the archive are expected to follow the 'YYYY-MM/DD/instrument/' convention.

    Args:

    date_range: (str): The date range as specified on the command line '--date_range' argument.
    instrument_dirs: (list of str) A list of instruments to find files for.

    Returns: A generator for the list of matching pathlib.Path objects.
    """
    start_date, end_date = parse_date_range(date_range)

    instrument_dirs = get_valid_instrument_dirs(instrument_dirs)

    # Go through the month directories
    for month_dir in lick_archive_config.ingest.archive_root_dir.iterdir():
        if month_dir.is_dir():
            # This should be a directory of the format YYYY-MM
            match = re.match(r"^(\d\d\d\d)-(\d\d)$", month_dir.name)
            if match is not None:
                year = int(match.group(1))
                month = int(match.group(2))
                # Go through the day directories
                for day_dir in month_dir.iterdir():
                    if (
                        day_dir.is_dir()
                        and re.match(r"^\d\d$", day_dir.name) is not None
                    ):
                        day = int(day_dir.name)
                        # Build a date object and if it's between the requested date range (inclusive), keep searching this
                        # directory
                        current_date = date(year, month, day)
                        if start_date is None or (
                            current_date >= start_date and current_date <= end_date
                        ):
                            # Go through instrument directories
                            for instrument_dir in day_dir.iterdir():
                                # Return any files found for the requested instruments
                                if (
                                    instrument_dir.is_dir()
                                    and instrument_dir.name in instrument_dirs
                                ):
                                    yield instrument_dir


def read_id_file(file: Path | str) -> list[int]:
    """Read a file containing database ids. The ids are integers that can be separated by any whitespace
    character.

    Args:
        file: The file to read the ids from.

    Return: A sorted list of database ids, these are the primary key for the FileMetadata table.
    """
    # Read the id list
    id_list = []
    line = 1
    with open(file, "r") as f:
        for line in f:
            for id in line.strip().split():
                id_list.append(int(id))

    return list(sorted(set(id_list)))
