from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_utils import django_db_setup


# Class to mock the ScheduleDB get_public_dates
class MockScheduleDB:

    mock_public_dates_data = {
        1: timedelta(days=-1000),
        3: timedelta(days=1000),
        4: timedelta(days=2000),
    }
    UNKNOWN_USER = -101
    PUBLIC_USER = -100

    def get_public_dates(self, telescope, observing_night, observerids):
        # All mock dates are relative to the current date so the tests don't break in the future
        current_date = date.today()
        return [
            (
                obid,
                (
                    current_date + self.mock_public_dates_data[obid]
                    if obid in self.mock_public_dates_data
                    else None
                ),
            )
            for obid in observerids
        ]

    def getOwnerhintMap(self):
        return {"bob": 4}


def mock_compute_ownerhint(observing_night, telescope, ownerhints):
    """Function to mock the lick external compute_ownerhint function"""
    from lick_archive import external

    if "public" in ownerhints:
        return (
            [external.ScheduleDB.PUBLIC_USER] + mock_compute_ownerhint.desired_obids,
            mock_compute_ownerhint.desired_coverids,
        )
    elif "fail" in ownerhints:
        raise RuntimeError("Test Exception")
    return (
        mock_compute_ownerhint.desired_obids,
        mock_compute_ownerhint.desired_coverids,
    )


# Fixture to load override access files to the test sqlite3 db
@pytest.fixture
def override_access_in_db(django_db):
    test_data_dir = Path(__file__).parent / "test_data"
    subdir = "2012-01/18/shane"

    from lick_archive.authorization.override_access import OverrideAccessFile

    oaf0 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.access")
    oaf1 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.1.access")
    oaf3 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.3.access")

    from lick_archive.apps.archive_auth import api

    api.save_oaf_to_db(oaf0)
    api.save_oaf_to_db(oaf1)
    api.save_oaf_to_db(oaf3)

    yield

    # Clean up the DB afterwards
    from lick_archive.apps.archive_auth.models import DBOverrideAccessFile

    DBOverrideAccessFile.objects.all().delete()


def test_set_auth_metadata(monkeypatch):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access

        # Mock the schedule db get_public_dates
        m.setattr(user_access, "ScheduleDB", MockScheduleDB)

        # Mock set_access_metadata to return the result of what set_auth_metadata does
        def mock_set_access_metadata(file_metadata, input_access):
            return input_access

        m.setattr(user_access, "set_access_metadata", mock_set_access_metadata)

        # File metadata to test with
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        file_metadata = FileMetadata(
            filename="2012-01/02/shane/r36.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=2,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # An access object that the mock identify_access will return
        access = user_access.Access(
            observing_night=date(year=2012, month=1, day=2),
            file_metadata=file_metadata,
            visibility=user_access.Visibility.PROPRIETARY,
            ownerids=[],
            coverids=[],
            reason=[],
        )

        def mock_identify_access(file_metadata):
            return access

        m.setattr(user_access, "identify_access", mock_identify_access)

        # Start out with a user (2) that has no public date, so that the default date range of two years will take effect
        # Since the observing night is in 2012, this will definitely be public
        access.ownerids = [3, 2]
        result_access = user_access.set_auth_metadata(file_metadata)
        # Make sure the monkey patch worked and returned an Access object
        assert isinstance(result_access, user_access.Access)
        assert result_access.visibility == user_access.Visibility.PUBLIC
        assert result_access.public_date == date(
            year=2014, month=1, day=2
        )  # Two years after obs date
        assert result_access.reason[0].startswith(
            "Rule 0: File has passed default proprietary end date"
        )

        # Test where the earliest public date (on obid 1) is in the past
        access.ownerids = [1, 3, 4]
        access.visibility = user_access.Visibility.PROPRIETARY
        access.reason = []
        result_access = user_access.set_auth_metadata(file_metadata)

        assert result_access.visibility == user_access.Visibility.PUBLIC
        assert (
            result_access.public_date
            == MockScheduleDB().get_public_dates("blah", "blah", [1])[0][1]
        )
        assert result_access.reason[0].startswith(
            "Rule 0: File has passed observer 1's proprietary end date"
        )

        # Test where it isn't public
        access.ownerids = [3, 4]
        access.visibility = user_access.Visibility.PROPRIETARY
        access.reason = []
        result_access = user_access.set_auth_metadata(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.public_date is not None
        assert result_access.reason[0].startswith("Rule 0: File is not public")
        assert result_access.reason[0].endswith("observer 3.")

        # Test where there are no observers
        access.ownerids = []
        access.visibility = user_access.Visibility.DEFAULT
        access.reason = []
        access.public_date = None
        result_access = user_access.set_auth_metadata(file_metadata)

        assert result_access.visibility == user_access.Visibility.PUBLIC
        assert result_access.public_date is None
        assert result_access.reason[0] == "Rule 6: No observers found for file"


def test_set_access_metadata():

    from lick_archive import external
    from lick_archive.authorization.user_access import (
        Access,
        Visibility,
        set_access_metadata,
    )
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.metadata.data_dictionary import FrameType, Instrument, Telescope

    # File metadata to test with
    file_metadata = FileMetadata(
        filename="2012-01/02/shane/r36.fits",
        telescope=Telescope.SHANE,
        instrument=Instrument.KAST_RED,
        obs_date=datetime(
            year=2012, month=1, day=2, hour=1, minute=1, second=1, tzinfo=timezone.utc
        ),
        frame_type=FrameType.science,
        public_date=date(year=9999, month=12, day=31),
    )

    # An access object with the authorization metadata
    access = Access(
        observing_night=date(year=2012, month=1, day=2),
        file_metadata=file_metadata,
        visibility=Visibility.PUBLIC,
        ownerids=[],
        coverids=["COVER1", "COVER2"],
        reason=[],
    )

    # Test a public file
    updated_metadata = set_access_metadata(file_metadata, access)

    assert updated_metadata.coversheet == "COVER1;COVER2"
    assert updated_metadata.public_date == date(year=2012, month=1, day=2)
    assert len(file_metadata.user_access) == 1
    assert file_metadata.user_access[0].obid == external.ScheduleDB.PUBLIC_USER

    # Test a proprietary file
    access = Access(
        observing_night=date(year=2012, month=1, day=2),
        file_metadata=file_metadata,
        visibility=Visibility.PROPRIETARY,
        ownerids=[3, 45],
        coverids=[],
        reason=["Rule 1: blah blah", "Rule 2: blah blah blah"],
        public_date=date(year=2013, month=1, day=2),
    )

    file_metadata.public_date = date(year=9999, month=12, day=31)
    file_metadata.coversheet = None

    updated_metadata = set_access_metadata(file_metadata, access)
    assert updated_metadata.coversheet is None
    assert updated_metadata.public_date == date(year=2013, month=1, day=2)

    assert len(file_metadata.user_access) == 2

    assert file_metadata.user_access[0].obid == 3
    assert (
        file_metadata.user_access[0].reason
        == "Rule 1: blah blah\nRule 2: blah blah blah"
    )

    assert file_metadata.user_access[1].obid == 45
    assert (
        file_metadata.user_access[1].reason
        == "Rule 1: blah blah\nRule 2: blah blah blah"
    )

    # Test an blank publicationd date, which should be UNKNOWN
    access = Access(
        observing_night=date(year=2012, month=1, day=2),
        file_metadata=file_metadata,
        visibility=Visibility.DEFAULT,
        ownerids=[],
        coverids=[],
        reason=["Rule 1: blah blah", "Rule 2: blah blah blah"],
        public_date=None,
    )

    file_metadata.public_date = date(year=1970, month=1, day=1)
    file_metadata.user_access = []
    updated_metadata = set_access_metadata(file_metadata, access)

    assert updated_metadata.public_date == date(year=9999, month=12, day=31)
    assert len(file_metadata.user_access) == 1

    from lick_archive.external import ScheduleDB

    assert file_metadata.user_access[0].obid == ScheduleDB.UNKNOWN_USER
    assert (
        file_metadata.user_access[0].reason
        == "Rule 1: blah blah\nRule 2: blah blah blah"
    )

    # Test an UNKNOWN file with a public_date (that should be overridden)
    access = Access(
        observing_night=date(year=2012, month=1, day=2),
        file_metadata=file_metadata,
        visibility=Visibility.UNKNOWN,
        ownerids=[],
        coverids=[],
        reason=["Rule 1: blah blah", "Rule 2: blah blah blah"],
        public_date=date(year=1970, month=1, day=1),
    )

    file_metadata.public_date = date(year=1970, month=1, day=1)
    file_metadata.user_access = []
    updated_metadata = set_access_metadata(file_metadata, access)

    assert updated_metadata.public_date == date(year=9999, month=12, day=31)
    assert len(file_metadata.user_access) == 1

    from lick_archive.external import ScheduleDB

    assert file_metadata.user_access[0].obid == ScheduleDB.UNKNOWN_USER
    assert (
        file_metadata.user_access[0].reason
        == "Rule 1: blah blah\nRule 2: blah blah blah"
    )


@django_db_setup
def test_identify_access_rule1_query_failure(monkeypatch):
    with monkeypatch.context() as m:
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/02/shane/r36.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=2,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # First test a failure when querying
        from lick_archive.apps.archive_auth import api

        def mock_failed_get_related_override_files(filepath):
            raise RuntimeError("Test failure")

        m.setattr(
            api, "get_related_override_files", mock_failed_get_related_override_files
        )

        from lick_archive.authorization import user_access

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert (
            result_access.reason[0]
            == "Rule 1z: Failed when querying for override access."
        )


@django_db_setup
def test_identify_access_rule1_all_observers(
    monkeypatch, tmp_path, override_access_in_db
):

    with monkeypatch.context() as m:
        m.chdir(tmp_path)

        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [35, 88]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/shane/b2345.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        result_access = user_access.identify_access(file_metadata)

        # This should be identified as an arc frame, and given access to all users on that night
        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.reason[0].startswith(
            "Rule 1a: All observers from the night included"
        )
        assert file_metadata.frame_type == FrameType.arc
        assert sorted(result_access.ownerids) == [35, 88]
        assert sorted(result_access.coverids) == ["COVER1", "COVER2"]


@django_db_setup
def test_identify_access_rule1_public(monkeypatch, override_access_in_db):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [35, 88]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/shane/b34.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # Test a public file
        result_access = user_access.identify_access(file_metadata)
        assert result_access.visibility == user_access.Visibility.PUBLIC
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert (
            result_access.reason[0]
            == "Rule 1b: Override access file gave public visibility."
        )


@django_db_setup
def test_identify_access_rule1_proprietary(monkeypatch, override_access_in_db):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [3]
        mock_compute_ownerhint.desired_coverids = ["COVER1"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/shane/r34.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.ownerids == [3]
        assert result_access.coverids == ["COVER1"]
        assert result_access.reason[0].startswith(
            "Rule 1b/c/d: Scheduled observer for ownerhint1"
        )
        assert result_access.reason[1].startswith(
            "Rule 1b/c/d: Found 1 observers and 1 coverids"
        )


@django_db_setup
def test_identify_access_rule1_obstype_and_2a(monkeypatch, override_access_in_db):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [35, 88]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/shane/r2345.jpg",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.arc,
            public_date=date(year=9999, month=12, day=31),
        )

        # Test overriding non-calib type. This also tests rule 2a, always public suffixes
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PUBLIC
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert file_metadata.frame_type == FrameType.science
        assert result_access.reason[0].startswith(
            "Rule 1a: No special rule for obstype"
        )
        assert result_access.reason[1].startswith(
            "Rule 2a: Suffix jpg is public for instrument"
        )


@django_db_setup
def test_identify_access_public_fixed_owner():
    from lick_archive.authorization import user_access
    from lick_archive.db.archive_schema import FileMetadata
    from lick_archive.metadata.data_dictionary import FrameType, Instrument, Telescope

    # File metadata to test with
    file_metadata = FileMetadata(
        filename="2012-01/18/AOsample/s2345.fits",
        telescope=Telescope.SHANE,
        instrument=Instrument.AO_SAMPLE,
        obs_date=datetime(
            year=2012, month=1, day=19, hour=1, minute=1, second=1, tzinfo=timezone.utc
        ),
        frame_type=FrameType.arc,
        public_date=date(year=9999, month=12, day=31),
    )

    # A public fixed owner
    result_access = user_access.identify_access(file_metadata)

    assert result_access.visibility == user_access.Visibility.PUBLIC
    assert result_access.ownerids == []
    assert result_access.coverids == []
    assert result_access.reason[0].startswith("Rule 2b: Fixed public owner")


@django_db_setup
def test_identify_access_private_fixed_owner(monkeypatch):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [35]
        mock_compute_ownerhint.desired_coverids = ["COVER1"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/PEAS/s2345.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.PEAS,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.arc,
            public_date=date(year=9999, month=12, day=31),
        )

        # A proprietary fixed owner
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.ownerids == [35]
        assert result_access.coverids == ["COVER1"]
        assert result_access.reason[0].startswith("Rule 2b: Scheduled observer")
        assert result_access.reason[1].startswith(
            "Rule 2b: Found 1 observers and 1 coverids"
        )

        # An unknown fixed owner
        mock_compute_ownerhint.desired_obids = []
        mock_compute_ownerhint.desired_coverids = []

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0].startswith(
            "Rule 2b: Found 0 observers and 0 coverids"
        )
        assert result_access.reason[1].startswith("Rule 2z: Unknown fixed owner")


@django_db_setup
def test_identify_access_rule3(monkeypatch):

    with monkeypatch.context() as m:
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Mock compute_ownerhint
        mock_compute_ownerhint.desired_obids = [35, 36]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        # File metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/18/AOsample/s2345.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.SHARCS,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.arc,
            public_date=date(year=9999, month=12, day=31),
        )

        # Calibrations are visible to everyone that night
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert sorted(result_access.ownerids) == [35, 36]
        assert sorted(result_access.coverids) == ["COVER1", "COVER2"]
        assert result_access.reason[0].startswith(
            "Rule 3: All observers from the night can access frame type: arc"
        )
        assert result_access.reason[1].startswith(
            "Rule 3: Scheduled observer for all-observers"
        )
        assert result_access.reason[2].startswith(
            "Rule 3: Found 2 observers and 2 coverids"
        )


@django_db_setup
def test_identify_access_rule4_query_failure(tmp_path, monkeypatch):
    # Test failure to call gshow (or gshow returns failure)
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        from lick_archive.config.archive_config import ArchiveConfigFile

        lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        lick_archive_config.authorization.gshow_path = (
            Path(__file__).parent / "mock_gshow.py"
        )

        file_metadata = FileMetadata(
            filename="2012-01/18/AOsample/s2345.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.SHARCS,
            obs_date=datetime(
                year=2012,
                month=1,
                day=19,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # Without an input file, the mock gshow returns an error
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0].startswith(
            "Rule 4z: Failed to query for OWNRHINT"
        )


@django_db_setup
def test_identify_access_rule4_using_mtime(tmp_path, monkeypatch):

    with monkeypatch.context() as m:
        m.chdir(tmp_path)

        from lick_archive.config.archive_config import ArchiveConfigFile

        lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

        from lick_archive import external
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        lick_archive_config.authorization.gshow_path = (
            Path(__file__).parent / "mock_gshow.py"
        )

        # Start with an empty gshow output
        mock_gshow_output = tmp_path / "mock_gshow_output.txt"
        with open(mock_gshow_output, "w") as f:
            print("1234 <undef>", file=f)

        # Clear the timed cache of gshow output
        external.get_keyword_ownerhints.cache.clear()

        # Test for something with no beginning and end date in the header
        # for that we need a header
        file_metadata = FileMetadata(
            filename="2018-11/20/AO/s0066.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.SHARCS,
            obs_date=datetime(
                year=2018,
                month=11,
                day=20,
                hour=20,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        test_data_dir = Path(__file__).parent / "test_data"
        file = test_data_dir / "2018-11_20_AO_s0066-hdu0.txt"
        with open(file, "r") as f:
            file_metadata.header = f.read()

        # Test a file with no beginning/end date, and no stat
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0].startswith(
            "Rule 4v: No mtime information in db."
        )

        # Now test with an actual stat time
        # This time was chosen because it is useful for later in this test
        file_metadata.mtime = datetime.fromisoformat("2019-05-03T09:28:32.740+00:00")

        # Mock compute_ownerhint so rule 5 doesn't interfere
        mock_compute_ownerhint.desired_obids = []
        mock_compute_ownerhint.desired_coverids = []

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.DEFAULT
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0] == "Rule 4b: No ownerhints found."
        assert (
            result_access.reason[1]
            == "Rule 5: Found 0 observers and 0 coverids from override access ownerhints: all-observers"
        )

        # Now test with a file that has a DATE-BEG and DATE-END, but no ownerhints from gshow
        # This file's header info:
        # DATE-BEG= '2019-05-03T09:28:29.74' / OBSERVATION BEGIN
        # DATE-END= '2019-05-03T09:28:30.74' / OBSERVATION END
        # OBJECT  = 'HACN143arc        '
        # Test for something with no beginning and end date in the header
        # for that we need a header
        file_metadata = FileMetadata(
            filename="2019-05/02/shane/r684.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2019,
                month=5,
                day=2,
                hour=20,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            mtime=datetime.fromisoformat("2019-05-03T09:28:32.740+00:00"),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        test_data_dir = Path(__file__).parent / "test_data"
        file = test_data_dir / "2019-05_02_shane_r684-hdu0.txt"
        with open(file, "r") as f:
            file_metadata.header = f.read()

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.DEFAULT
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0] == "Rule 4b: No ownerhints found."
        assert (
            result_access.reason[1]
            == "Rule 5: Found 0 observers and 0 coverids from override access ownerhints: all-observers"
        )

        # Test for something with an ownerhint before the mtime
        # to do this we set the ownerhints returned from gshow to be before the header's DATE-BEG, and also our mock mtime,
        # (which is set to 2s after DATE-BEG)
        with open(mock_gshow_output, "w") as f:
            print(
                "1556874929   hint1", file=f
            )  # 2019-05-03T09:15:29.740+00:00, 13 minutes before DATE-BEG
            print(
                "1556875229   hint2", file=f
            )  # 2019-05-03T09:20:29.740+00:00, 8 minutes before DATE-BEG

        # For the above to take effect the cache must be cleared
        external.get_keyword_ownerhints.cache.clear()

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert (
            result_access.reason[0]
            == "Rule 4b: Found 0 observers and 0 coverids from override access ownerhints: hint2"
        )
        assert result_access.reason[1] == "Rule 4y: No owner found for ownerhint: hint2"

        # Now test with an actual owner found
        mock_compute_ownerhint.desired_obids = [35]
        mock_compute_ownerhint.desired_coverids = ["COVER1"]
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.ownerids == [35]
        assert result_access.coverids == ["COVER1"]
        assert result_access.reason[0].startswith(
            "Rule 4b: Scheduled observer for hint2"
        )
        assert (
            result_access.reason[1]
            == "Rule 4b: Found 1 observers and 1 coverids from override access ownerhints: hint2"
        )


@django_db_setup
def test_identify_access_rule4_using_header_times(monkeypatch, tmp_path):
    # Test identify_access where gshow results fall in between a file's beginning/end time
    with monkeypatch.context() as m:
        m.chdir(tmp_path)

        from lick_archive.config.archive_config import ArchiveConfigFile

        lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

        from lick_archive import external
        from lick_archive.authorization import user_access
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        lick_archive_config.authorization.gshow_path = (
            Path(__file__).parent / "mock_gshow.py"
        )

        # Test with a file that has a DATE-BEG and DATE-END
        # This file's header info:
        # DATE-BEG= '2019-05-03T09:28:29.74' / OBSERVATION BEGIN
        # DATE-END= '2019-05-03T09:28:30.74' / OBSERVATION END
        # OBJECT  = 'HACN143arc        '
        file_metadata = FileMetadata(
            filename="2019-05/02/shane/r684.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2019,
                month=5,
                day=2,
                hour=20,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # We need a header for the file_metadata with DATE-BEG/DATE-END
        test_data_dir = Path(__file__).parent / "test_data"
        file = test_data_dir / "2019-05_02_shane_r684-hdu0.txt"
        with open(file, "r") as f:
            file_metadata.header = f.read()

        # Gshow output is 2019-05-03T09:28:30.
        mock_gshow_output = tmp_path / "mock_gshow_output.txt"
        with open(mock_gshow_output, "w") as f:
            print("1556875710 hint1", file=f)
            print("1556875710 hint2", file=f)

        # Clear the timed cache of gshow output
        external.get_keyword_ownerhints.cache.clear()

        # Stat shouldn't be called in this case, we make sure of that with a mock that always fails

        def mock_failed_stat(self, *args, **kwargs):
            raise RuntimeError("Test exception")

        m.setattr(user_access.Path, "stat", mock_failed_stat)

        # Test a file with beginning/end date, and multiple ownerhints
        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.UNKNOWN
        assert result_access.ownerids == []
        assert result_access.coverids == []
        assert result_access.reason[0].startswith(
            "Rule 4w: Multiple ownerhints for file:"
        )

        # Now test with only one hint, returning an actual user

        with open(mock_gshow_output, "w") as f:
            print("1556875710 hint1", file=f)

        # Clear the timed cache of gshow output
        external.get_keyword_ownerhints.cache.clear()

        mock_compute_ownerhint.desired_obids = [36]
        mock_compute_ownerhint.desired_coverids = ["COVER1"]

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)

        result_access = user_access.identify_access(file_metadata)

        assert result_access.visibility == user_access.Visibility.PROPRIETARY
        assert result_access.ownerids == [36]
        assert result_access.coverids == ["COVER1"]
        assert result_access.reason[0].startswith(
            "Rule 4a: Scheduled observer for hint1"
        )
        assert (
            result_access.reason[1]
            == "Rule 4a: Found 1 observers and 1 coverids from override access ownerhints: hint1"
        )


def test_apply_ownerhints(monkeypatch):

    with monkeypatch.context() as m:
        mock_compute_ownerhint.desired_obids = []
        mock_compute_ownerhint.desired_coverids = []

        from lick_archive.authorization import user_access

        m.setattr(user_access, "compute_ownerhint", mock_compute_ownerhint)
        m.setattr(user_access, "ScheduleDB", MockScheduleDB)

        from lick_archive import external
        from lick_archive.authorization.user_access import (
            Access,
            Visibility,
            apply_ownerhints,
        )
        from lick_archive.db.archive_schema import FileMetadata
        from lick_archive.metadata.data_dictionary import (
            FrameType,
            Instrument,
            Telescope,
        )

        # Get some file metadata to test with
        file_metadata = FileMetadata(
            filename="2012-01/02/shane/r36.fits",
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_RED,
            obs_date=datetime(
                year=2012,
                month=1,
                day=2,
                hour=1,
                minute=1,
                second=1,
                tzinfo=timezone.utc,
            ),
            frame_type=FrameType.science,
            public_date=date(year=9999, month=12, day=31),
        )

        # The access object to apply owner hints to
        access = Access(
            observing_night=date(year=2012, month=1, day=2),
            file_metadata=file_metadata,
            visibility=Visibility.DEFAULT,
            ownerids=[],
            coverids=[],
            reason=[],
        )

        # Test a failure
        apply_ownerhints(access, "1", ["fail"])
        assert access.ownerids == []
        assert access.coverids == []
        assert access.visibility == Visibility.UNKNOWN
        assert access.reason[0].startswith(
            "Rule 1: Observing calendar ownerhint query failed"
        )

        # Test with one ownerid found, and no ownerhints passed
        mock_compute_ownerhint.desired_obids = [1]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]
        access.visibility = Visibility.DEFAULT
        access.reason = []

        apply_ownerhints(access, "1", [])
        assert access.ownerids == mock_compute_ownerhint.desired_obids
        assert sorted(access.coverids) == mock_compute_ownerhint.desired_coverids

        assert access.visibility == Visibility.PROPRIETARY
        assert access.reason[0].startswith("Rule 1: Scheduled observer")
        assert access.reason[1].startswith("Rule 1: Found 1 observers and 2 coverids")

        # Test with two owner ids found, and one ownerhint passed
        mock_compute_ownerhint.desired_obids = [1, 2]
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["hint1"])

        assert access.ownerids == []
        assert access.coverids == []
        assert access.visibility == Visibility.DEFAULT
        assert (
            access.reason[1]
            == "Rule 1: Observing calendar ownerhint query returned multiple users for ownerhint hint1, ignoring it."
        )
        assert access.reason[2].startswith("Rule 1: Found 0 observers and 0 coverids")

        # Test with two ownerids returned, and all-observers passed, no coverids
        mock_compute_ownerhint.desired_coverids = []
        mock_compute_ownerhint.desired_obids = [1, 2]
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["all-observers"])

        assert sorted(access.ownerids) == mock_compute_ownerhint.desired_obids
        assert access.coverids == mock_compute_ownerhint.desired_coverids
        assert access.visibility == Visibility.PROPRIETARY
        assert access.reason[0].startswith("Rule 1: Scheduled observer")
        assert access.reason[1].startswith("Rule 1: Found 2 observers and 0 coverids")

        # Test the "Public ownerhint pattern"
        mock_compute_ownerhint.desired_obids = [1, 2]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["hint1", "RECUR_X100"])

        assert access.ownerids == []
        assert sorted(access.coverids) == mock_compute_ownerhint.desired_coverids
        assert access.visibility == Visibility.PUBLIC
        assert (
            access.reason[-2]
            == "Rule 1: Observing calendar ownerhint query returned public user."
        )
        assert access.reason[-1].startswith("Rule 1: Found 3 observers and 2 coverids")

        # Test unscheduled user
        from lick_archive.apps.archive_auth.models import ArchiveUser

        bob_user = ArchiveUser(
            username="bob", last_name="bob", email="bob@example.org", obid=4
        )
        bob_user.save()
        mock_compute_ownerhint.desired_obids = [external.ScheduleDB.UNKNOWN_USER]
        mock_compute_ownerhint.desired_coverids = []
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT

        apply_ownerhints(access, "1", ["bob"], allow_unscheduled=True)

        assert access.ownerids == [4]
        assert access.coverids == []
        assert access.visibility == Visibility.PROPRIETARY
        assert access.reason[0] == "Rule 1: Unscheduled observer bob found. obsid 4"
        assert access.reason[1].startswith("Rule 1: Found 1 observers and 0 coverids")

        # Test unrecognized unscheduled observer
        mock_compute_ownerhint.desired_obids = [external.ScheduleDB.UNKNOWN_USER]
        mock_compute_ownerhint.desired_coverids = []
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["robert"], allow_unscheduled=True)

        assert access.ownerids == []
        assert access.coverids == []
        assert access.visibility == Visibility.DEFAULT
        assert access.reason[0] == "Rule 1: Could not find observer for robert"
        assert (
            access.reason[1]
            == "Rule 1: Observing calendar ownerhint query returned unknown user."
        )
        assert access.reason[2].startswith("Rule 1: Found 0 observers and 0 coverids")

        # Test Unknown user and one known user
        mock_compute_ownerhint.desired_obids = [external.ScheduleDB.UNKNOWN_USER, 3]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["all-observers"])

        assert access.ownerids == [3]
        assert sorted(access.coverids) == mock_compute_ownerhint.desired_coverids
        assert access.visibility == Visibility.PROPRIETARY
        assert access.reason[0] == "Rule 1: Could not find observer for all-observers"
        assert access.reason[1].startswith("Rule 1: Found 1 observers and 2 coverids")

        # Test Unknown user
        mock_compute_ownerhint.desired_obids = [external.ScheduleDB.UNKNOWN_USER]
        mock_compute_ownerhint.desired_coverids = ["COVER1", "COVER2"]
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["all-observers"])

        assert access.ownerids == []
        assert sorted(access.coverids) == mock_compute_ownerhint.desired_coverids
        assert access.visibility == Visibility.DEFAULT
        assert access.reason[0] == "Rule 1: Could not find observer for all-observers"
        assert access.reason[1].startswith(
            "Rule 1: Observing calendar ownerhint query returned unknown user."
        )
        assert access.reason[2].startswith("Rule 1: Found 0 observers and 2 coverids")

        # Test no owners found
        mock_compute_ownerhint.desired_obids = []
        access.ownerids = []
        access.coverids = []
        access.reason = []
        access.visibility = Visibility.DEFAULT
        apply_ownerhints(access, "1", ["all-observers"])

        assert access.ownerids == []
        assert sorted(access.coverids) == mock_compute_ownerhint.desired_coverids
        assert access.visibility == Visibility.DEFAULT
        assert access.reason[0].startswith("Rule 1: Found 0 observers and 2 coverids")
