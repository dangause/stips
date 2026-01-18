import enum
from datetime import date, datetime

from astropy.coordinates import SkyCoord
from astropy.table import Table, vstack


class OrderedEnum(enum.Enum):
    """An ordered enumeration class taken from the Python documentation at
    https://docs.python.org/3/library/enum.html.

    This class is used to make enumerations support comparison operators, so that
    they can be grouped and sorted.
    """

    def __ge__(self, other):
        """Support >= operator for enumerations"""
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented

    def __gt__(self, other):
        """Support > operator for enumerations"""
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __le__(self, other):
        """Support <= operator for enumerations"""
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other):
        """Support < operator for enumerations"""
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


class FrameType(enum.Enum):
    dark = "dark"
    flat = "flat"
    bias = "bias"
    science = "science"
    arc = "arc"
    calib = "calibration"
    focus = "focus"
    unknown = "unknown"


class IngestFlags(enum.IntFlag):
    CLEAR = 0  # Nothing of interest when ingesting the file
    NO_LAMPS_IN_HEADER = (
        1  # No lamps were specified in the header, so OBJECT was used to find the type
    )
    AO_NO_DATE_BEG = 2  # A Shane AO/ShARCS file had no DATE_BEG
    AO_USE_DATE_OBS = (
        4  # A Shane AO/ShARCS file had used DATE_OBS, which is less reliable
    )
    USE_DIR_DATE = 8  # The obs date for a file was determined by the directory name, so is only accurate to 24 hours.
    NO_OBJECT_IN_HEADER = 16  # There was no OBJECT in the header
    NO_FITS_END_CARD = 32  # The FITS header had no END card
    NO_FITS_SIMPLE_CARD = 64  # The FITS header had no SIMPLE card at the beginning.
    FITS_VERIFY_ERROR = 128  # The FITS header failed a verification check.
    UNKNOWN_FORMAT = 256  # The FITS file could not be identified (used internally, should not be inserted to DB).
    NO_COORD = 512  # The RA/DEC in the header could be parsed, so cone searches will not match it.
    INVALID_CHAR = (
        1024  # An invalid character (such as '\x00') was found in the header.
    )


class Telescope(enum.Enum):
    SHANE = "Shane"
    APF = "APF"
    NICKEL = "Nickel"


class Instrument(enum.Enum):
    # If the values for these enum's change, the values in archive_config.ini also need to be changed.
    # TODO, merge Kast Red/Kast Blue?
    KAST_RED = "Kast Red"
    KAST_BLUE = "Kast Blue"
    SHARCS = "ShaneAO/ShARCS"
    ALL_SKY = "All Sky"
    AO_SAMPLE = "AOsample"
    AO_TEL = "AOtelemetry"
    APF_CAM = "APF Cam"
    APF = "APF"
    APF_GUIDE = "APF Guide"
    CAT = "CAT"
    GEMINI = "Gemini"
    HAM120 = "Ham 120"
    HAM_CAM1 = "HamCam 1"
    HAM_CAM2 = "HamCam 2"
    NICKEL = "Nickel"
    PEAS = "PEAS"
    PFCAM = "PF Cam"
    SKYCAM2 = "SkyCam 2"


# Constants to prevent typos in group names
class Category(OrderedEnum):
    COMMON = "Common Fields"
    SHANE_KAST = "Shane Kast Specific"
    SHARCS = "Shane AO/ShARCS Specific"


# Allow for some type concepts that python's type system doesn't have but is useful for databases
class LargeInt(int):
    """An integer that is too big for a standard database ``integer`` type."""

    pass


class LargeStr(str):
    """A string that is too large for a standard database ``varchar`` type."""

    pass


MAX_PUBLIC_DATE = date(9999, 12, 31)
MIN_PUBLIC_DATE = date(1970, 1, 1)
MAX_FILENAME_SIZE = 256
MAX_OBJECT_SIZE = 256
MAX_FILENAME_BATCH = 1000

data_dictionary = Table(
    names=["db_name", "human_name", "type", "category", "description"],
    dtype=["<U63", "U", "O", Category, "U"],
    rows=[
        ["id", "Internal Id", int, Category.COMMON, "Unique integer ID of the file."],
        ["telescope", "Telescope", Telescope, Category.COMMON, "Name of telescope."],
        [
            "instrument",
            "Instrument",
            Instrument,
            Category.COMMON,
            "Name of instrument.",
        ],
        [
            "obs_date",
            "Observation Date",
            datetime,
            Category.COMMON,
            "UTC Observation date and time.",
        ],
        [
            "exptime",
            "Exposure Time",
            float,
            Category.COMMON,
            "Exposure time in seconds.",
        ],
        [
            "ra",
            "Right Ascension",
            str,
            Category.COMMON,
            "Right Ascension as it appears in the FITS header.",
        ],
        [
            "dec",
            "Declination",
            str,
            Category.COMMON,
            "Declination as it appears in the FITS header.",
        ],
        [
            "coord",
            "",
            SkyCoord,
            Category.COMMON,
            "pgSphere SPOINT value used for searching for ra/dec.",
        ],
        [
            "object",
            "Object",
            str,
            Category.COMMON,
            "Name/description of object being observed.",
        ],
        ["airmass", "Airmass", float, Category.COMMON, "Airmass of the observation."],
        [
            "frame_type",
            "Frame Type",
            FrameType,
            Category.COMMON,
            "Type of the observation.",
        ],
        [
            "filename",
            "File Name",
            str,
            Category.COMMON,
            "Relative filename and path within the archive filesystem.",
        ],
        [
            "program",
            "Program",
            str,
            Category.COMMON,
            "The name of the program the observation was taken for.",
        ],
        [
            "coversheet",
            "Coversheet Id",
            str,
            Category.COMMON,
            "The coversheet id(s) the observation was taken for.",
        ],
        [
            "observer",
            "Observers",
            str,
            Category.COMMON,
            "The name or names of the person taking the observation.",
        ],
        [
            "ingest_flags",
            "",
            IngestFlags,
            Category.COMMON,
            "A bit field value indicating any issues during ingest. See TBD.",
        ],
        [
            "file_size",
            "File size",
            LargeInt,
            Category.COMMON,
            "The size of the file (in bytes).",
        ],
        [
            "mtime",
            "File Modification Time",
            datetime,
            Category.COMMON,
            "The date and time the file was last modified.",
        ],
        [
            "public_date",
            "Date File Becomes Public",
            date,
            Category.COMMON,
            "The date the file became/will become accesible to the public.",
        ],
        [
            "header",
            "Header",
            LargeStr,
            Category.COMMON,
            "The full header information from the file in plain text format.",
        ],
        ["slit_name", "Slit Name", str, Category.SHANE_KAST, "The slit name."],
        [
            "beam_splitter_pos",
            "Beam Splitter Position",
            str,
            Category.SHANE_KAST,
            "The beam splitter position",
        ],
        [
            "grism",
            "Grism  (Blue only)",
            str,
            Category.SHANE_KAST,
            "The grism used. Only applies to Kast Blue.",
        ],
        [
            "grating_name",
            "Grating Name  (Red only)",
            str,
            Category.SHANE_KAST,
            "The grating used. Only applies to Kast Red.",
        ],
        [
            "grating_tilt",
            "Grating Tilt (Red only)",
            int,
            Category.SHANE_KAST,
            "The grating tilt used. Only applies to Kast Red.",
        ],
        [
            "apername",
            "Aperture Position",
            str,
            Category.SHARCS,
            "Dewar aperture wheel, named position",
        ],
        [
            "filter1",
            "Filter 1",
            str,
            Category.SHARCS,
            "Dewar filter wheel 1, named position",
        ],
        [
            "filter2",
            "Filter 2",
            str,
            Category.SHARCS,
            "Dewar filter wheel 2, named position",
        ],
        [
            "sci_filter",
            "Science Filter",
            str,
            Category.SHARCS,
            "External (warm) science filter wheel position",
        ],
        ["coadds_done", "Number of Coadds", int, Category.SHARCS, "Number of coadds."],
        [
            "true_int_time",
            "True Integration Time",
            float,
            Category.SHARCS,
            "True integration time in seconds per coadd",
        ],
    ],
)

# Dynamic fields created by the API but not stored in the database
dynamic_fields = Table(
    names=["db_name", "human_name", "type", "category", "description"],
    dtype=["<U63", "U", "O", Category, "U"],
    rows=[
        [
            "download_link",
            "Download Link",
            str,
            Category.COMMON,
            "URL for downloading the file.",
        ],
    ],
)


api_capabilities = {
    "required": data_dictionary[
        [
            True if db_name in ["filename", "obs_date", "object", "coord"] else False
            for db_name in data_dictionary["db_name"]
        ]
    ],
    "sort": data_dictionary[
        [
            True if db_name not in ["coord", "header", "ingest_flags"] else False
            for db_name in data_dictionary["db_name"]
        ]
    ],
    "result": vstack(
        [
            data_dictionary[
                [
                    True if db_name not in ["coord", "ingest_flags"] else False
                    for db_name in data_dictionary["db_name"]
                ]
            ],
            dynamic_fields,
        ]
    ),
}

# The units for fields where applicable.
field_units = {
    "obs_date": "date",
    "exptime": "seconds",
    "ra": "angle",
    "dec": "angle",
    "file_size": "bytes",
    "mtime": "date",
    "true_int_time": "seconds",
}

supported_instruments = [Instrument.KAST_BLUE, Instrument.KAST_RED, Instrument.SHARCS]
