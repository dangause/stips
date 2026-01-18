import logging

logger = logging.getLogger(__name__)

import subprocess
from datetime import date, datetime, timedelta, timezone

from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.metadata.data_dictionary import Telescope
from lick_archive.utils.timed_cache import timed_cache

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


@timed_cache(timedelta(hours=1))
def get_keyword_ownerhints(
    telescope: Telescope, observing_night: date
) -> list[tuple[datetime, str]]:
    """Get the ownerhints for the given observing night. This method is cached and will only query for values
    once an hour.

    Args:
        telescope:          The telescope to query on.
        observing_night:    The observing night to query on. This should be based in the UTC-8
                            timezone, noon to noon.

    Returns:
        A list of tuples containing the date/time of the ownerhint and the ownerhint. The list is sorted
        by datetime.
    """

    # Build the arguments needed to call gshow
    gshow = str(lick_archive_config.authorization.gshow_path)

    schedule_service = lick_archive_config.authorization.schedule_services[
        telescope.value
    ]

    gshow_cmd = [
        gshow,
        "-s",
        schedule_service,
        "OWNRHINT",
        "-date",
        observing_night.strftime("%Y-%m-%d 12:00:00"),
        "-window",
        "24hr",
        "-resolution",
        "0",
        "-timeformat",
        "%s",
        "-format",
        "%.0s%s%.0s",
        "-noredi",
        "-dbuser",
        "user",
    ]

    # Call gshow with a 10s timeout
    logger.info(f"Calling {' '.join(gshow_cmd)}")
    result = subprocess.run(
        gshow_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to run 'gshow', error code: {result.returncode}")

    logger.info(f"gshow output:\n{result.stdout}")

    # Process the results. Output lines should be:
    # <timestamp> <OWNERHINT value>
    # We'll ignore any lines that don't match
    # A value of "<undef>" is a special value meaning no ownerhint, so it is also ignored
    results = []

    for line in result.stdout.splitlines():
        try:
            split_line = line.split()
            if len(split_line) == 2:
                if split_line[1] == "<undef>":
                    logger.debug(f"Ignoring <undef> line: '{line}'")
                else:
                    results.append(
                        (
                            datetime.fromtimestamp(int(split_line[0]), tz=timezone.utc),
                            split_line[1],
                        )
                    )
            else:
                logger.debug(f"Ignoring unrecognized line: '{line}'")
        except Exception:
            logger.debug(
                f"Ignorning unrecognized line: '{line}'. Received exception.",
                exc_info=True,
            )

    # Sort the results by time
    results.sort(key=lambda x: x[0])
    return results
