import logging

logger = logging.getLogger(__name__)

import calendar
from datetime import date, datetime, timedelta, timezone

from dateutil.parser import parse
from lick_archive.config.archive_config import ArchiveConfigFile, ProprietaryPeriod
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.metadata import metadata_utils

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


def calculate_public_date(
    file_date: date | datetime, prop_period: ProprietaryPeriod
) -> date:
    """Calculate the date a file's proprietary period
    expires given it's date and the proprietary period.

    This function attempts to be friendly in terms of how the propreitary
    period is specified. It attempts to do intuitive arithmetic
    by years or months, and accepts units as singular or plural strings.

    For example::

        2023-01-01 + "1 month"  = 2023-02-01
        2024-01-31 + "1 month"  = 2024-03-01  # Skip to next month because Feb 2024 doesn't have 31 days
        2024-01-31 + "2 months" = 2024-03-31
        2024-02-29 + "1 years"  = 2025-03-01  # Feb 2025 is not a leap year, so skip to the next month
        2024-02-29 + "4 years"  = 2028-02-29

    Args:
        file_date:  The observation date of the file.
        period:     The proprietary period as a string. The format of this string is "<n> <units>" where
                    n is an integer, and <units> is one of "years", "year", "month", "months", "days", "day".
                    Units is case insensitive.

    Return:
        The date the files becomes public.
    """
    # TODO can I replace this with dateutil?
    if isinstance(file_date, datetime):
        file_date = file_date.date()

    if prop_period.value < 1:
        # A 0 proprietary period means there's no proprietary period. The file became public on the date it was taken.
        return file_date

    if prop_period.unit == ProprietaryPeriod.PeriodUnit.DAYS:
        # Just use the default time delta behavior
        return file_date + timedelta(days=prop_period.value)
    else:
        # Figure out the total # of years and months in the period
        if prop_period.unit == ProprietaryPeriod.PeriodUnit.YEARS:
            period_years = prop_period.value
            period_months = 0
        elif prop_period.unit == ProprietaryPeriod.PeriodUnit.MONTHS:
            period_years = int(prop_period.value / 12)
            period_months = prop_period.value % 12

        public_year = file_date.year + period_years
        public_month = file_date.month + period_months

        # Wrap months around to the next year
        if public_month > 12:
            public_year += 1
            public_month -= 12

        # Make sure the date isn't beyond the end of the month
        # I wasn't sure how to handle this, so I decided to make it
        # the first of the next month, so that Feb 29
        # is handled as March 1st on subsequent non-leap years
        weekday_of_first, days_in_month = calendar.monthrange(public_year, public_month)
        if file_date.day > days_in_month:
            public_day = 1
            public_month += 1
            if public_month == 13:
                public_year += 1
                public_month = 1
        else:
            public_day = file_date.day

        return date(year=public_year, month=public_month, day=public_day)


def get_file_begin_end_times(file_metadata: FileMetadata):
    """Get the beginning/end observation times from file metadata"""
    beg_time, end_time = None, None

    try:
        # TODO: This won't work with multi HDU files. Maybe just add DATE-BEG/DATE-END to file_metadata?
        header = metadata_utils.get_hdul_from_string([file_metadata.header])[0].header

        if "DATE-BEG" in header:
            beg_time = parse(header["DATE-BEG"] + "+00:00")

        if "DATE-END" in header:
            end_time = parse(header["DATE-END"] + "+00:00")
    except Exception:
        # TODO, if when we support Non-FITS files this should detect that and
        # return without logging an error
        logger.error(
            f"Could get read FITS header from {file_metadata.filename}", exc_info=True
        )

    return beg_time, end_time


def get_observing_night(observation_datetime: datetime) -> date:
    """Get the date of the observing night
    from an observation datetime (potentially in any timezone but probably UTC).
    The observing night is in Pacific Standard Time (UTC-8), Noon to Noon.

    Args:
        observation_datetime: A timezone aware observation date.

    Return: The date of the observing night.
    """
    if observation_datetime.utcoffset() is None:
        raise ValueError(
            f"Expecting a timezone aware datetime, received {observation_datetime}"
        )

    # Use a "lick standard time" of UTC-(8+12) to represent a timezone for the date
    lst = timezone(timedelta(hours=-(8 + 12)))

    return observation_datetime.astimezone(lst).date()
