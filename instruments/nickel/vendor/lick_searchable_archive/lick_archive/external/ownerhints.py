import logging

logger = logging.getLogger(__name__)

from datetime import date, timedelta

from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.external import ScheduleDB
from lick_archive.metadata.data_dictionary import Telescope
from lick_archive.utils.timed_cache import timed_cache

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


@timed_cache(timedelta(hours=1))
def compute_ownerhint(
    observing_night: date, telescope: Telescope, ownerhint: str
) -> tuple[list[int], list[str]]:
    """Attempt to find ownerids for a given telescope and observing night using ownerhints. It uses series of hueristics
    defined in the lroot schedule module.

    This method is cached and will only query for values once an hour

    Args:
        observing_night: The observing night to query for.
        telescope:       The telescope to query for.
        ownerhint:      Any ownerhints that are available to help find the ownerids. This can be an empty string.
    """
    # Import the LROOT code for computing ownerhints
    from schedule import ownercompute, schedconfig

    # Configure the schedule module code used to query for ownerhints
    cfgp = schedconfig.SchCfg().configparse
    if "database" not in cfgp:
        cfgp.add_section("database")
    cfgp.set("database", "database", lick_archive_config.authorization.sched_db_name)
    cfgp.set("database", "hostname", lick_archive_config.authorization.sched_db_host)
    username, password = (
        lick_archive_config.authorization.read_user_information().split(":")
    )
    cfgp.set("database", "username", username)
    cfgp.set("database", "password", password)
    cfgp.set("database", "timeout", "5")

    # ownerhintcompute sometimes returns duplicates, we use a set for cover_ids/observer_ids to filter those out
    cover_ids = []
    observer_ids = []
    # Use ownerhintcompute from the lroot schedule module to search for each ownerhint
    if ownerhint == "all-observers":
        ownerhint = ""

    # Build the input arguments
    telescope_info = ScheduleDB().get_telescope_info(telescope)
    ownerHintDict = {
        "teleId": telescope_info["teleid"],
        "csid0": telescope_info["csid0"],
        "calnight": observing_night.isoformat(),
        "OWNRHINT": ownerhint,
    }
    ownercompute.ownerhintcompute(ownerHintDict, True)

    # The output was placed in ownerHintDict
    if ownerHintDict["COVERID"] is not None:
        cover_ids += ownerHintDict["COVERID"].split()

    if ownerHintDict["OWNERIDS"] is not None:
        observer_ids += [int(x) for x in ownerHintDict["OWNERIDS"].split()]

    return observer_ids, cover_ids
