import logging

logger = logging.getLogger(__name__)

from lick_archive.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

from lick_archive.lick_schedule import ScheduleDB


def test_get_observers():
    sched_db = ScheduleDB()

    observers = sched_db.get_observers()

    assert len(observers) > 0

    # Verify observers have required fields, and log user names for
    # inspection later with "pytest --log-level DEBUG -s --log-file test.log"
    for observer in observers:
        assert "obid" in observer and isinstance(observer["obid"], int)
        assert (
            "lastname" in observer
            and isinstance(observer["lastname"], str)
            and len(observer["lastname"]) > 0
        )
        logger.info(f"obid:{observer['obid']: 5d} lastname: {observer['lastname']}")
