"""
Common utility functions for reading metadata from fits files
"""

import logging

logger = logging.getLogger(__name__)
from pathlib import Path

from astropy.io import fits

from lick_archive.db.pgsphere import SPoint


def safe_header(header, key):
    """Read a keyword from a header, returning None if it's not there."""
    if key in header:
        return header[key]
    else:
        return None


def safe_strip(string_or_none):
    """Strip the leading and trailing whitespace from a string, ignoring None values."""
    if string_or_none is not None:
        return string_or_none.strip()


def parse_file_name(filename: Path | str):
    """
    Parse lick archive filenames to get the date and instrument from the path the file was stored under.
    The format of the filename is expected to be 'YYYY-MM/DD/instrument/file
    """
    if isinstance(filename, str):
        filename = Path(filename)
    day = filename.parent.parent.name
    year_month = filename.parent.parent.parent.name
    instr = filename.parent.name
    return f"{year_month}-{day}", instr


def get_shane_lamp_status(header):
    """Translate the LAMPSTAX header keywords in shane files to an array
    of booleans."""
    lamp_names = [
        "1",
        "2",
        "3",
        "4",
        "5",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
    ]

    try:
        lamp_status = [
            (isinstance(header[f"LAMPSTA{name}"], bool) and header[f"LAMPSTA{name}"])
            or (
                isinstance(header[f"LAMPSTA{name}"], str)
                and header[f"LAMPSTA{name}"].lower() == "on"
            )
            for name in lamp_names
        ]
    except KeyError:
        lamp_status = None
    return lamp_status


def get_ra_dec(header):
    """Read RA and DEC coordinates from a fits header, prioritizing the
    WCS keywords first, and falling back to 'RA' and 'DEC' if those
    are not set.

    Returns:

    ra (str): The RA in string format
    dec (str): The DEC in string format
    coord (SPoint): The coordinates as a SPoint object suitable
                    for inserting into a pgsphere column
    """
    ra = None
    dec = None
    coord = None

    if (
        "CRVAL1S" in header
        and "CRVAL2S" in header
        and "CTYPE1S" in header
        and "CTYPE2S" in header
        and "WCSNAMES" in header
    ):
        # Make sure the WCS is really celestial
        # Note the FITS standard says the first four characters
        # are for type and are padded with hyphens
        if (
            header["WCSNAMES"] == "Celestial coordinates"
            and header["CTYPE1S"].startswith("RA--")
            and header["CTYPE2S"].startswith("DEC-")
        ):

            ra = header["CRVAL1S"]
            dec = header["CRVAL2S"]

    if (
        ra is None
        and "CRVAL1" in header
        and "CRVAL2" in header
        and "CTYPE1" in header
        and "CTYPE2" in header
        and "WCSNAME" in header
    ):
        # Make sure the WCS is really celestial
        # Note the FITS standard says the first four characters
        # are for type and are padded with hyphens
        if (
            header["WCSNAME"] == "Celestial coordinates"
            and header["CTYPE1"].startswith("RA--")
            and header["CTYPE2"].startswith("DEC-")
        ):

            ra = header["CRVAL1"]
            dec = header["CRVAL2"]

    if ra is None and "RA" in header and "DEC" in header:
        ra = header["RA"]
        dec = header["DEC"]

    if isinstance(ra, str):
        ra = ra.strip()

    if isinstance(dec, str):
        dec = dec.strip()

    if ra is not None and dec is not None:
        try:
            coord = SPoint(ra, dec)
            if coord.ra is None or coord.dec is None:
                coord = None
        except Exception:
            logger.info("Failed to create SPoint from ra/dec: {e}", exc_info=True)
            coord = None
    return (ra, dec, coord)


class _MockHDU:
    """Mock HDU object for unit testing.
    If any of our code starts touching data, a real HDU object may be needed
    """

    def __init__(self, header):
        self.header = header


def get_hdul_from_text(text_files):
    """
    Build a simulated HDU list from headers written to text files
    """

    hdul = []
    for file in text_files:
        hdul.append(
            _MockHDU(fits.Header.fromfile(file, sep="\n", endcard=False, padding=False))
        )

    return hdul


def get_hdul_from_string(string_list):
    """
    Build a simulated HDU list from headers written to text files
    """

    hdul = []
    for header_string in string_list:
        hdul.append(_MockHDU(fits.Header.fromstring(header_string, sep="\n")))

    return hdul
