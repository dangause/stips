"""
Reads metadata from files for ingest into the archive.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from astropy.io import fits

# Add each new MetadataReader subclass here
# Importing each reader registers them as a subclass
from lick_archive.authorization import user_access
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.metadata.abstract_reader import AbstractReader
from lick_archive.metadata.data_dictionary import IngestFlags

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

logger = logging.getLogger(__name__)


def open_fits_file(file_path):
    """
    Opens a fits file, attempting to deal with invalid files as much as possible.

    Args:
    file_path (pathlib.Path or str):
        Path to the file to open.

    Return (tuple of astropy.io.fits.HDUList, archive_schema.IngestFlags):
        The HDUL from the opened fits file and the IngestFlags documenting any issues
        opening the file. The HDUL will be None and ingest_flags UNKNOWN_FORMAT bit
        set if the file couldn't be opened.

    raises: Exception: Exceptions raised for unexpected errors openiong the file.

    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    ingest_flags = IngestFlags.CLEAR
    hdul = None
    ignore_missing_end = False
    ignore_missing_simple = False
    while True:
        try:
            hdul = fits.open(
                file_path,
                ignore_missing_end=ignore_missing_end,
                ignore_missing_simple=ignore_missing_simple,
            )
            hdul.verify("exception")
            break
        except OSError as e:
            if len(e.args) == 1:
                # Probably a special error from astropy
                if e.args[0] == "Header missing END card.":
                    if ignore_missing_end is True:
                        logger.error(
                            f"{file_path} missing end card, even though told to ignore it. Assume this isn't a FITS file."
                        )
                        ingest_flags |= IngestFlags.UNKNOWN_FORMAT
                        break
                    else:
                        logger.error(
                            f"{file_path} missing end card, will retry opening it."
                        )
                        ingest_flags |= IngestFlags.NO_FITS_END_CARD
                        ignore_missing_end = True

                elif e.args[0].startswith("No SIMPLE card found"):
                    if ignore_missing_simple is True:
                        logger.error(
                            f"{file_path} missing SIMPLE card, even though told to ignore it. Assume this isn't a FITS file."
                        )
                        ingest_flags |= IngestFlags.UNKNOWN_FORMAT
                        break
                    else:
                        logger.error(
                            f"{file_path} missing SIMPLE card, will retry opening it."
                        )
                        ignore_missing_simple = True
                        ingest_flags |= IngestFlags.NO_FITS_SIMPLE_CARD

                else:
                    logger.error(f"{file_path} could not be opened, error: {e.args[0]}")
                    ingest_flags |= IngestFlags.UNKNOWN_FORMAT
                    break
            else:
                # Unknown non-astropy error, re-raise
                raise

        except fits.verify.VerifyError:
            ingest_flags |= IngestFlags.FITS_VERIFY_ERROR
            break
        except Exception:
            raise RuntimeError(f"Failed to open {file_path}.")

    return hdul, ingest_flags


def read_file(file_path):
    """
    Reads metadata from a file.

    Args:
        file_path (pathlib.Path, or str):
            The path of the file to read. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>), as the directory name may be used
            to help identifying the instrument that created the file.
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    hdul = None
    try:
        hdul, ingest_flags = open_fits_file(file_path)
        if hdul is not None and (ingest_flags & IngestFlags.UNKNOWN_FORMAT) == 0:
            row = read_hdul(file_path, hdul, ingest_flags)
            if row is None:
                # The file was a FITS file, but not from a source currently
                # supported for ingest
                raise ValueError(f"Unknown FITS file: {file_path}")

            return row
        else:
            # When non-fits file formats are supported, they would be dealt with here
            raise ValueError(f"Unknown file format: {file_path}")

    finally:
        if hdul is not None:
            hdul.close()


def read_hdul(file_path, hdul, ingest_flags):
    """
    Read a row of metadata from a FITS HDUList.

    This function was split from read_row so that it could also be used
    for updating (migrating) existing database rows using the "header"
    column already stored in the database, or be used by unit tests
    reading header data from text files.

    Args:
    file_path (pathlib.Path, or str):
        The path of the file the HDUList was read from. This should be in the
        Lick Archive directory format (YYYY-MM/DD/<instrument>/<file>), as the
        directory name may be used to help identifying the instrument that
        created the file.

    hdul (astropy.io.fits.HDUList):
        The HDUList with the header metadata for the file.

    ingest_flags (archive_schema.IngestFlags):
        Any ingest bit flags that were set during the process of opening a FITS file.

    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Ask each AbstractReader subclass if it can handle the file, and use it
    # if it can
    for child in AbstractReader.__subclasses__():
        if child.can_read(file_path, hdul):
            row = child().read_row(file_path, hdul, ingest_flags)

            # Try to set the file size and mtime, but leave them as None if needed
            try:
                st_info = (
                    file_path.stat()
                    if not file_path.is_symlink()
                    else file_path.lstat()
                )
                row.file_size = st_info.st_size
                row.mtime = datetime.fromtimestamp(st_info.st_mtime, tz=timezone.utc)
            except Exception:
                logger.warning(
                    f"Failed to get file size/modification time info for {file_path}, leaving as None",
                    exc_info=True,
                )
                row.file_size = None
                row.mtime = None

            return user_access.set_auth_metadata(row)

    return None
