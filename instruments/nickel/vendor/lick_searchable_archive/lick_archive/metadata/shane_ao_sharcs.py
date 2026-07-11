"""
MetadataReader implementation for Shane AO/ShARCS data.
"""

import logging
from datetime import date

from dateutil.parser import parse

from lick_archive.db.archive_schema import FileMetadata
from lick_archive.metadata.abstract_reader import AbstractReader
from lick_archive.metadata.data_dictionary import (
    FrameType,
    IngestFlags,
    Instrument,
    Telescope,
)
from lick_archive.metadata.metadata_utils import (
    get_ra_dec,
    get_shane_lamp_status,
    parse_file_name,
    safe_header,
)

logger = logging.getLogger(__name__)


class ShaneAO_ShARCS(AbstractReader):
    @classmethod
    def can_read(cls, file_path, hdul):
        """
        Determine if a file is ShaneAO/ShARCS data.

        Args:

        file_path (pathlib.Path):
            Path to the file to check. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>).

        hdul (None or astropy.io.fits.HDUList):
            An HDUList object from the file.

        Returns (bool): True if the file is ShaneAO/Sharcs data, False if it is not.
        """
        filename_date, instr = parse_file_name(file_path)
        if instr == "AO":
            file_date_parts = filename_date.split("-")
            file_date = date(
                year=int(file_date_parts[0]),
                month=int(file_date_parts[1]),
                day=int(file_date_parts[2]),
            )
            # Based inspecting data in the archive, there's no ShARCS data before april 2014
            # This differentiates it from older IRCAL data
            if file_date >= date(year=2014, month=4, day=1):
                return True

        return False

    def determine_frame_type(self, object, filter2, caly_name, lamps):
        """
        Determine the frame type of a file.

        Args:
        object (str):    The object field from the header.
        filter2 (str):   The filter2 field from the header.
        caly_name (str): The CALY_NAME field from the header.
        lamps (list of bool):  The lamp status as returned by metadata_utils.get_shane_lamp_status.

        Returns tuple (FrameType, IngestFlags): The frame type of the file, and any ingest flags
                                                set from determining the frame type.

        """
        ingest_flags = IngestFlags.CLEAR
        frame_type = FrameType.unknown
        if filter2 == "Blank25":
            frame_type = FrameType.dark
        elif caly_name is not None and caly_name in ("Red Light", "Argon"):
            frame_type = FrameType.arc
        elif lamps is not None and any(lamps[0:5]):
            # If any dome lights are on this is considered a flat
            # Per an e-mail from Ellie Gates, only the flat lamps matter for ShARCS,
            # with lamps 5 and 2 being the most often used and others used rarely.
            # The TUB lamps (higher than lamp 5) are not used.
            frame_type = FrameType.flat

        # Keep track of whether the lamps is present so the ingest_flags are correct
        if lamps is None:
            ingest_flags = ingest_flags | IngestFlags.NO_LAMPS_IN_HEADER
            logger.debug("No Lamps in header.")

        # If the above does not determine the type, use the object
        if frame_type == FrameType.unknown:

            if object is not None:
                if "dark" in object.lower() and filter2 is None:
                    # Don't set it to dark if filter2 is actually in the header
                    frame_type = FrameType.dark
                elif "flat" in object.lower():
                    frame_type = FrameType.flat
                elif "arc" in object.lower():
                    frame_type = FrameType.arc
                elif len(object.strip()) > 0:
                    frame_type = FrameType.science
                else:
                    ingest_flags = ingest_flags | IngestFlags.NO_OBJECT_IN_HEADER

            else:
                ingest_flags = ingest_flags | IngestFlags.NO_OBJECT_IN_HEADER

        return (frame_type, ingest_flags)

    def read_row(self, file_path, hdul, ingest_flags=IngestFlags.CLEAR):
        """Read an SQL Alchemy row of metadata from a file.

        Args:

        file_path (pathlib.Path):
            The path of the file to read. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>).

        hdul (None or astropy.io.fits.HDUList):
            An HDUList from the file.

        ingest_flags (archive_schema.IngestFlags):
            Any ingest bit flags that were set during the process of opening a FITS file.

        Returns (archive_schema.FileMetadata): A row of metadata read from the file.

        Raises: Exception raised if the file is corrupt or lacks required metadata.
        """

        header = hdul[0].header
        m = FileMetadata()
        m.telescope = Telescope.SHANE
        m.instrument = Instrument.SHARCS

        # Parse the observation date as an iso date, adding +00:00 to make it UTC

        m.obs_date = None
        date_beg = safe_header(header, "DATE-BEG")
        if date_beg is not None:
            logger.debug("Found DATE-BEG")
            try:
                m.obs_date = parse(date_beg + "+00:00")
            except ValueError:
                logger.error(f"Invalid format for DATE-BEG: {date_beg}")

        # Check for weird out of sync DATE-OBS
        if m.obs_date is None:
            ingest_flags = ingest_flags | IngestFlags.AO_NO_DATE_BEG
            filename_date, instr = parse_file_name(file_path)
            date_obs = safe_header(header, "DATE-OBS")
            if date_obs is not None and date_obs == filename_date:
                time_obs = safe_header(header, "TIME-OBS")
                if time_obs is not None:
                    try:
                        m.obs_date = parse(f"{date_obs}T{time_obs}+00:00")
                        ingest_flags = ingest_flags | IngestFlags.AO_USE_DATE_OBS
                    except ValueError:
                        logger.error(
                            f"Invalid format for DATE-OBS/TIME-OBS: {date_obs}/{time_obs}"
                        )

                    logger.debug(
                        "Did not find DATE-BEG, but DATE-OBS/TIME-OBS seem sane, using those"
                    )
            else:
                logger.debug(
                    "DATE-OBS is on a different day than the directory name, not using."
                )

        if m.obs_date is None:
            logger.debug("Using directory date for observation date.")
            ingest_flags = ingest_flags | IngestFlags.USE_DIR_DATE
            # Use noon Lick time (aka UTC-8)
            m.obs_date = parse(f"{filename_date}T12:00:00-08:00")

        m.coadds_done = safe_header(header, "COADDONE")
        m.true_int_time = safe_header(header, "TRUITIME")
        if m.true_int_time is not None and m.coadds_done is not None:
            m.exptime = m.true_int_time * m.coadds_done
        else:
            m.exptime = None

        (m.ra, m.dec, m.coord) = get_ra_dec(header)
        if m.coord is None:
            ingest_flags = ingest_flags | IngestFlags.NO_COORD

        m.object = safe_header(header, "OBJECT")
        m.slit_name = None
        m.airmass = safe_header(header, "AIRMASS")
        m.beam_splitter_pos = None
        m.grism = None
        m.grating_name = None
        m.grating_tilt = None
        m.filename = str(file_path)
        m.apername = safe_header(header, "APERNAM")
        m.filter1 = safe_header(header, "FILT1NAM")
        m.filter2 = safe_header(header, "FILT2NAM")
        m.sci_filter = safe_header(header, "SCIFILT")
        m.program = safe_header(header, "PROGRAM")
        m.observer = safe_header(header, "OBSERVER")
        lamp_status = get_shane_lamp_status(header)
        (m.frame_type, frame_flags) = self.determine_frame_type(
            m.object, m.filter2, safe_header(header, "CALYNAM"), lamp_status
        )
        ingest_flags |= frame_flags
        m.ingest_flags = f"{ingest_flags:032b}"
        m.header = header.tostring(sep="\n", endcard=False, padding=False)

        return m
