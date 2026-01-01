# Test the date arithmetic used to calculate the date a file
# leaves it's proprietary period
import pytest


def test_invalid_period():

    from lick_archive.config.archive_config import ProprietaryPeriod

    with pytest.raises(ValueError, match="Invalid proprietary period"):
        public_date = ProprietaryPeriod("year")

    with pytest.raises(ValueError, match="Invalid proprietary period"):
        public_date = ProprietaryPeriod("")

    with pytest.raises(ValueError, match="Invalid proprietary period"):
        public_date = ProprietaryPeriod("3 to 4 years")

    with pytest.raises(
        ValueError, match="Proprietary period does not contain a valid integer"
    ):
        public_date = ProprietaryPeriod("a year")

    with pytest.raises(
        ValueError, match="Proprietary period does not contain a valid integer"
    ):
        public_date = ProprietaryPeriod("1.1 years")

    with pytest.raises(ValueError, match="Proprietary period must be >= 0 -1 years"):
        public_date = ProprietaryPeriod("-1 years")

    with pytest.raises(ValueError, match="Incorrect proprietary period units given"):
        public_date = ProprietaryPeriod("1 centon")


def test_calculate_public_date():

    from datetime import date

    from lick_archive.authorization.user_access import calculate_public_date
    from lick_archive.config.archive_config import ProprietaryPeriod

    # Test the basics, with singular and plural units, mixed case
    file_date = date(2023, 1, 10)
    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 year"))
    assert public_date == date(2024, 1, 10)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("3 Years"))
    assert public_date == date(2026, 1, 10)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 month"))
    assert public_date == date(2023, 2, 10)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("6 Months"))
    assert public_date == date(2023, 7, 10)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("28 months"))
    assert public_date == date(2025, 5, 10)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 Day"))
    assert public_date == date(2023, 1, 11)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("30 days"))
    assert public_date == date(2023, 2, 9)

    # Test around leap year and days past the end of month
    file_date = date(2023, 2, 28)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 day"))
    assert public_date == date(2023, 3, 1)

    file_date = date(2024, 2, 28)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 day"))
    assert public_date == date(2024, 2, 29)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("2 Days"))
    assert public_date == date(2024, 3, 1)

    file_date = date(2024, 2, 29)
    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 Year"))
    assert public_date == date(2025, 3, 1)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("4 years"))
    assert public_date == date(2028, 2, 29)

    file_date = date(2024, 1, 31)
    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 Month"))
    assert public_date == date(2024, 3, 1)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("2 months"))
    assert public_date == date(2024, 3, 31)

    file_date = date(2024, 12, 31)
    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 month"))
    assert public_date == date(2025, 1, 31)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("13 months"))
    assert public_date == date(2026, 1, 31)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("1 day"))
    assert public_date == date(2025, 1, 1)

    public_date = calculate_public_date(file_date, ProprietaryPeriod("0 years"))
    assert public_date == file_date
