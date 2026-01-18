import logging

logger = logging.getLogger(__name__)

import enum
import sys
from dataclasses import dataclass
from pathlib import Path

from lick_archive.config.config_base import (
    ConfigDict,
    ConfigFile,
    ConfigNamespace,
    ParsedURL,
)


class ArchiveSiteType(enum.Enum):
    SINGLE_HOST = "single_host"
    FRONTEND = "frontend"
    BACKEND = "backend"


@dataclass
class HostConfig(ConfigNamespace):
    """Configuration values that may vary by host"""

    config_section_name = "Host"

    type: ArchiveSiteType
    """The type of host"""

    app_names: list[str]
    """The apps deployed to the host"""

    url_path_prefix: str
    """Path prefix to use for archive URLs (e.g. example.org/prefix/<all archive URLs>)"""

    api_url: ParsedURL
    """The URL used to access the backend API"""

    frontend_url: ParsedURL
    """The URL used to access the frontend"""


@dataclass
class DatabaseConfig(ConfigNamespace):
    """Database configuratoin values"""

    config_section_name = "Database"

    archive_db: str
    """The name of the archive metadata database"""

    db_query_user: str
    """The name of the user queries should use. This user has read-only access."""

    db_ingest_user: str
    """The name of the user ingest should use. This user has read/write access."""


@dataclass
class QueryConfig(ConfigNamespace):
    """Query configuration"""

    config_section_name = "Query"

    file_header_url_format: str
    """The python string format for forming the URL to a file's header. The {} is replaced by the files relative path in the archive."""

    default_search_radius: str
    """Default search radius when searching by ra and dec. This can be in any format astropy.coordinates.Angle can recognize."""


class ProprietaryPeriod:
    """Representation of the archive's propreitary period, expressed in either days, months, or years.
    Note, this class only exists because Python's :class:`datetime.timedelta` does not support "years" as an argument.

    Args:
        propreitary_period:     The propreitary period string from the archive configuration file. It should have two whitespace separated
                                fields. The first is an integer >= 0 representing the time period and the second is a string representing the
                                units. The units can be "day", "days", "month", "months", "year" or "years" and is case insensitive.
    """

    class PeriodUnit(enum.Enum):
        DAYS = "days"
        MONTHS = "months"
        YEARS = "years"

    def __init__(self, proprietary_period: str):

        # Parse out the period and units
        period_list = proprietary_period.split()
        if len(period_list) != 2:
            raise ValueError(f"Invalid proprietary period {proprietary_period}")

        try:
            self.value = int(period_list[0])
        except ValueError:
            raise ValueError(
                f"Proprietary period does not contain a valid integer {proprietary_period}"
            )

        if self.value < 0:
            raise ValueError(f"Proprietary period must be >= 0 {proprietary_period}")

        units = period_list[1]

        # Check for days
        if units.lower() in ["days", "day"]:
            self.unit = ProprietaryPeriod.PeriodUnit.DAYS
        else:
            # Figure out the total # of years and months in the period
            if units.lower() in ["years", "year"]:
                self.unit = ProprietaryPeriod.PeriodUnit.YEARS
            elif units.lower() in ["months", "month"]:
                self.unit = ProprietaryPeriod.PeriodUnit.MONTHS
            else:
                raise ValueError(
                    f"Incorrect proprietary period units given: {proprietary_period}"
                )

    def __str__(self):
        return f"{self.value} {self.unit.value}"


@dataclass
class IngestConfig(ConfigNamespace):
    """Metadata ingest configuration."""

    config_section_name = "Ingest"

    archive_root_dir: Path
    """The root directory of the archive file system."""

    supported_directories: list[str]
    """The instrument directory names supported by the archive."""

    insert_batch_size: int
    """The number of new files to insert into the database per transaction."""


class FileTypes(ConfigDict):
    config_section_name = "File Types"
    default_key_name = "default"
    value_type = str


@dataclass
class DownloadConfig(ConfigNamespace):
    """Download configuration"""

    config_section_name = "Download"

    file_download_url_format: str
    """The python string format for forming the URL to a file's header. The {} is replaced by the files relative path in the archive."""

    max_tarball_files: int
    """The maxuimum number of files allowed to download in a tarball"""

    max_tarball_size: int
    """The maximum combined size of files allowed in a tarball. In MiB"""

    file_types: FileTypes
    """The MIME types for files per instrument."""


class TelescopeNames(ConfigDict):
    config_section_name = "Telescope Names"
    value_type = str


class FixedOwners(ConfigDict):
    config_section_name = "Fixed Owners"
    default_key_name = "default"
    value_type = str


class PublicSuffixes(ConfigDict):
    config_section_name = "Public Suffixes"
    default_key_name = "default"
    value_type = list[str]


class ScheduleServices(ConfigDict):
    config_section_name = "Schedule Services"
    value_type = str


@dataclass
class AuthConfig(ConfigNamespace):
    config_section_name = "Authorization"

    default_proprietary_period: ProprietaryPeriod
    """The default proprietary period for files."""

    sched_db_host: str
    """The schedule database host (with optional port specified after a colon)"""

    sched_db_name: str
    """The schedule database name"""

    sched_db_user_info: Path
    """Path to a text file containing the schedule database's user information, formatted as 'user:password'"""

    gshow_path: Path
    """Path to the gshow executable"""

    telescope_names: TelescopeNames
    """Mapping of instrument directory names to telescope names"""

    fixed_owners: FixedOwners
    """Mapping of instrument directory names to fixed owners for those files. Instruments not in the config file default to None for no
    fixed owner"""

    public_suffixes: PublicSuffixes
    """Mapping of instrument directory names to the suffixes (file extensions) that are always public"""

    public_observers: list
    """Observer names that are always public"""

    public_ownerhint_pattern: str
    """Regex used to determine which ownerhints are public"""

    schedule_services: ScheduleServices
    """Mapping of Telescope name to KTL schedule service name"""

    def read_user_information(self) -> str:
        """
        Read the username/password for the schedule database from the given text file.
        The information should be formatted: "username:password".
        """
        try:
            with open(self.sched_db_user_info, "r") as user_info:
                for line in user_info:
                    if ":" in line.strip():
                        user_info = line.strip()
                        return user_info
        except Exception:
            logger.error(
                f"Failed to read user schedule db user information from {self.sched_db_user_info}.",
                exc_info=True,
            )

        raise RuntimeError(
            f"Could not read schedule db user information. Make sure {self.sched_db_user_info} exists, is readable, and contains '<username>:<password>'"
        )


class ArchiveConfigFile(ConfigFile):
    config_classes = [
        HostConfig,
        DatabaseConfig,
        QueryConfig,
        IngestConfig,
        DownloadConfig,
        AuthConfig,
    ]

    @classmethod
    def load_from_standard_inifile(cls):
        # This relies on our current way of deploying the config into "etc" under a python virtual environment
        settings_file = (
            Path(sys.executable).parent.parent / "etc" / "archive_config.ini"
        )

        return cls.from_file(settings_file)
