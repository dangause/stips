"""
MetadataReader implementation for Shane Kast data.
"""

import logging

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
    safe_strip,
)

logger = logging.getLogger(__name__)


class ShaneKastReader(AbstractReader):
    """
    Reader implementation for Shane Kast data.
    """

    @classmethod
    def can_read(cls, file_path, hdul):
        """
        Determine if a file is Shane Kast data.

        Args:

        file_path (pathlib.Path):
            Path to the file to check. This should be in the Lick Archive directory
            format (YYYY-MM/DD/<instrument>/<file>).

        hdul (None or astropy.io.fits.HDUList):
            An HDUList from the file.

        Returns (bool): True if the file is supported, False if it is not.
        """

        if "shane" in str(file_path.parent):
            if safe_header(hdul[0].header, "VERSION") in ["kastr", "kastb"]:
                return True
            elif "INSTRUME" in hdul[0].header:
                instr = hdul[0].header["INSTRUME"]
                if instr.strip().upper() == "KAST":
                    # Older 2008 and earlier headers
                    return True

                program = safe_header(hdul[0].header, "PROGRAM")
                # Some headers had blank INSTRUME but KAST in the program
                if instr.strip().upper() == "" and program.strip().upper() == "KAST":
                    return True

        return False

    def determine_frame_type(self, exptime, lamps, object):
        """
        Determine the frame type based on exposure time, lamps and object name.
        Parts of this logic was adapted from PypeIt

        Args:
        exptime (float):      Exposure time in seconds.
        lamps (list of bool): The lamp status, as returned by metadata_utils.get_shane_lamp_status.
        object (str):         The OBJECT keyword from the file's header.

        Returns (FrameType, IngestFlags): A tuple with the frame type, and any ingest flags set
                                          while determining the frame type.
        """
        ingest_flags = IngestFlags.CLEAR
        if lamps is None:
            logger.debug("No lamps information, using OBJECT to determine frame type.")
            ingest_flags = ingest_flags | IngestFlags.NO_LAMPS_IN_HEADER
            if object is not None:
                if "flat" in object.lower():
                    frame_type = FrameType.flat
                elif "dark" in object.lower():
                    frame_type = FrameType.dark
                elif "arc" in object.lower():
                    frame_type = FrameType.arc
                elif "bias" in object.lower():
                    frame_type = FrameType.bias
                elif len(object.strip()) > 0:
                    frame_type = FrameType.science
                else:
                    ingest_flags = ingest_flags | IngestFlags.NO_OBJECT_IN_HEADER
                    frame_type = FrameType.unknown
            else:
                ingest_flags = ingest_flags | IngestFlags.NO_OBJECT_IN_HEADER
                frame_type = FrameType.unknown

        else:
            # If there are no lamps, it's science if it's > 1s exposure or
            # bias if it's less
            frame_type = FrameType.unknown
            if not any(lamps):
                if exptime > 1:
                    frame_type = FrameType.science

            # It's still bias if < 1s
            if exptime <= 1:
                frame_type = FrameType.bias
            else:
                if any([lamps[i] for i in range(0, 5)]):
                    # If any dome lights are on this is considered a flat
                    frame_type = FrameType.flat

                elif any([lamps[i] for i in range(5, 16)]):
                    # Check for arcs
                    if exptime <= 61:
                        frame_type = FrameType.arc

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

        # The newer shane kast examples I've seen have
        # VERSION set to kastr or kastb
        instrument = safe_header(header, "VERSION")
        if instrument == "kastb":
            m.instrument = Instrument.KAST_BLUE
        elif instrument == "kastr":
            m.instrument = Instrument.KAST_RED

        # The older examples have INSTRUME set to KAST and
        # use SPSIDE to indicate red/blue
        elif "INSTRUME" in header:
            instrument = header["INSTRUME"].strip().upper()
            # Some older data had a blank instrument, but program was still
            # Kast
            if (
                instrument == "KAST"
                or instrument == ""
                and safe_header(header, "PROGRAM").strip().upper() == "KAST"
            ):
                side = safe_header(header, "SPSIDE")
                if side is None:
                    raise ValueError(
                        "Could not ingest older Kast data because it did not have SPSIDE set."
                    )
                if side.strip().lower() == "red":
                    m.instrument = Instrument.KAST_RED
                elif side.strip().lower() == "blue":
                    m.instrument = Instrument.KAST_BLUE
                else:
                    raise ValueError(
                        f"Could not ingest older Kast data because the SPSIDE value {side} was not red or blue."
                    )
            else:
                raise ValueError(
                    f"Unrecognized instrument for Shane telescope: '{instrument}'."
                )
        else:
            raise ValueError(
                f"Unrecognized instrument for Shane telescope. Version was: '{instrument}'."
            )

        date_obs = safe_header(header, "DATE-OBS")
        if date_obs is None:
            logger.debug(f"Used file path for date for file {file_path}.")
            filename_date, instr = parse_file_name(file_path)
            # Use noon Lick time (aka UTC-8)
            m.obs_date = parse(f"{filename_date}T12:00:00-08:00")
            ingest_flags = ingest_flags | IngestFlags.USE_DIR_DATE
        else:
            # Parse the observation date as an iso date, adding +00:00 to make it UTC
            m.obs_date = parse(date_obs + "+00:00")

        m.exptime = safe_header(header, "EXPTIME")
        if m.exptime is None:
            # Some older examples use EXPOSURE
            m.exptime = safe_header(header, "EXPOSURE")

        (m.ra, m.dec, m.coord) = get_ra_dec(header)
        if m.coord is None:
            ingest_flags = ingest_flags | IngestFlags.NO_COORD

        m.object = safe_strip(safe_header(header, "OBJECT"))
        m.slit_name = safe_strip(safe_header(header, "SLIT_N"))
        m.airmass = safe_header(header, "AIRMASS")
        m.beam_splitter_pos = safe_strip(safe_header(header, "BSPLIT_N"))
        m.grism = safe_strip(safe_header(header, "GRISM_N"))
        m.grating_name = safe_strip(safe_header(header, "GRATNG_N"))
        m.grating_tilt = safe_header(header, "GRTILT_P")

        m.apername = None
        m.filter1 = None
        m.filter2 = None
        m.sci_filter = None
        m.program = safe_strip(safe_header(header, "PROGRAM"))
        m.observer = safe_strip(safe_header(header, "OBSERVER"))

        m.filename = str(file_path)

        lamp_status = get_shane_lamp_status(header)
        (m.frame_type, frame_flags) = self.determine_frame_type(
            m.exptime, lamp_status, m.object
        )

        ingest_flags |= frame_flags

        # Save the header for future updates, and
        # check for an invalid \x00 in the header string, which the DB rejects
        m.header = header.tostring(sep="\n", endcard=False, padding=False)
        if m.header.find("\x00") != -1:
            m.header = m.header.replace("\x00", " ")
            ingest_flags |= IngestFlags.INVALID_CHAR

        m.ingest_flags = f"{ingest_flags:032b}"
        return m
