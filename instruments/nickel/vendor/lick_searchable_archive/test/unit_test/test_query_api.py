# Test the archive API

import os
from datetime import date, datetime, timedelta

import pytest
from django.http import QueryDict
from lick_archive.db.archive_schema import Base, FileMetadata, UserDataAccess
from lick_archive.metadata.data_dictionary import FrameType
from rest_framework.exceptions import APIException
from rest_framework.serializers import ValidationError
from test_utils import (
    MockDatabase,
    basic_django_setup,
    create_mock_view,
    create_test_request,
)

not_public_date = date.today() + timedelta(days=30)

# Test rows shared between most tests
public_test_rows = [
    FileMetadata(
        telescope="Shane",
        instrument="Kast Blue",
        obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.arc,
        object=None,
        filename="/data/testfile1.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=date(1970, 1, 1),
    ),
    FileMetadata(
        telescope="Shane",
        instrument="Kast Blue",
        obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 1",
        filename="/data/testfile2.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=date(1970, 1, 1),
    ),
    FileMetadata(
        telescope="Shane",
        instrument="Kast Blue",
        obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 2",
        filename="/data/testfile3.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=date(1970, 1, 1),
    ),
    FileMetadata(
        telescope="Shane",
        instrument="Kast Blue",
        obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 2",
        filename="/data/testfile4.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=date(1970, 1, 1),
    ),
    FileMetadata(
        telescope="Shane",
        instrument="ShaneAO/ShARCS",
        obs_date=datetime(year=2022, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 2",
        filename="/data/testfile5.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=date(1970, 1, 1),
    ),
]

private_test_rows = [
    FileMetadata(
        telescope="Shane",
        instrument="ShaneAO/ShARCS",
        obs_date=datetime(year=2022, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 2",
        filename="/data/testfile6.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=not_public_date,
        user_access=[UserDataAccess(obid=1, reason="Test Reason")],
    ),
    FileMetadata(
        telescope="Shane",
        instrument="ShaneAO/ShARCS",
        obs_date=datetime(year=2022, month=6, day=1, hour=0, minute=0, second=0),
        frame_type=FrameType.science,
        object="object 2",
        filename="/data/testfile7.fits",
        ingest_flags="00000000000000000000000000000000",
        public_date=not_public_date,
        user_access=[UserDataAccess(obid=2, reason="Test Reason")],
    ),
]

test_rows = public_test_rows + private_test_rows


@basic_django_setup
def test_no_filters():
    """Test a query with no filters, which should fail"""

    request = create_test_request(path="files/", data=QueryDict("results=filename"))

    with MockDatabase(Base) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        with pytest.raises(
            APIException,
            match="At least one required field must be included in the query.",
        ):
            view.list(request)


@basic_django_setup
def test_filename_filter():
    """Test filtering on filename"""
    request = create_test_request(
        "files/", data=QueryDict("filename=eq,testfile1.fits&results=filename")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 2
        assert "id" in response.data["results"][0]
        # Note the view filters out the full path stored in the db
        assert response.data["results"][0]["filename"] == "testfile1.fits"


@basic_django_setup
def test_object_filter():
    """Test an exact object filter"""

    request = create_test_request(
        "files/",
        data=QueryDict("object=eq,object 2&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 3

        for i in range(2, len(public_test_rows)):
            assert len(response.data["results"][i - 2].keys()) == 3
            assert "id" in response.data["results"][i - 2]
            assert response.data["results"][i - 2]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i - 2]["object"] == public_test_rows[i].object
            )


@basic_django_setup
def test_proprietary_filter():
    """Test an exact object filter with loggin in users"""

    # A user that does not own anything, they'll only get public results
    request = create_test_request(
        "files/",
        data=QueryDict("object=eq,object 2&results=filename,object&sort=filename"),
        user="test_user3",
        obid=3,
    )

    # The public filenames matching "object 2"
    public_filenames = [
        os.path.basename(metadata.filename) for metadata in public_test_rows[2:5]
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 3
        for i in range(3):
            assert response.data["results"][i]["object"] == "object 2"

            assert response.data["results"][i]["filename"] in public_filenames

    # A user that owns one file. They'll get public results + the extra file
    request = create_test_request(
        "files/",
        data=QueryDict("object=eq,object 2&results=filename,object&sort=filename"),
        user="test_user2",
        obid=2,
    )
    all_filenames = public_filenames + ["testfile7.fits"]
    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)
        assert len(response.data["results"]) == 4
        for i in range(3):
            assert response.data["results"][i]["object"] == "object 2"

            assert response.data["results"][i]["filename"] in all_filenames

    # A super user that owns nothing. As a superuser they'll get all files that match the query
    request = create_test_request(
        "files/",
        data=QueryDict("object=eq,object 2&results=filename,object&sort=filename"),
        user="test_user2",
        obid=4,
        is_superuser=True,
    )
    all_filenames = public_filenames + [
        os.path.basename(metadata.filename) for metadata in private_test_rows
    ]
    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)
        assert len(response.data["results"]) == 5
        for i in range(3):
            assert response.data["results"][i]["object"] == "object 2"

            assert response.data["results"][i]["filename"] in all_filenames


@basic_django_setup
def test_startswith_filter():
    """Test filtering with a string prefix"""

    request = create_test_request(
        "files/",
        data=QueryDict("object=sw,object&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 4

        for i in range(1, len(public_test_rows)):
            assert len(response.data["results"][i - 1].keys()) == 3
            assert "id" in response.data["results"][i - 1]
            assert response.data["results"][i - 1]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i - 1]["object"] == public_test_rows[i].object
            )


@basic_django_setup
def test_contains_filter():
    """Test filtering with a substring"""

    request = create_test_request(
        "files/",
        data=QueryDict("object=cn,ject 1&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == os.path.basename(
            public_test_rows[1].filename
        )
        assert response.data["results"][0]["object"] == public_test_rows[1].object


@basic_django_setup
def test_case_insensitive_filter():
    """Test case insensitive filtering"""

    request = create_test_request(
        "files/",
        data=QueryDict("object=eqi,OBJECT 2&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 3

        for i in range(2, len(public_test_rows)):
            assert len(response.data["results"][i - 2].keys()) == 3
            assert "id" in response.data["results"][i - 2]
            assert response.data["results"][i - 2]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i - 2]["object"] == public_test_rows[i].object
            )

    request = create_test_request(
        "files/",
        data=QueryDict("object=swi,OBJECT&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 4

        for i in range(1, len(public_test_rows)):
            assert len(response.data["results"][i - 1].keys()) == 3
            assert "id" in response.data["results"][i - 1]
            assert response.data["results"][i - 1]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i - 1]["object"] == public_test_rows[i].object
            )

    request = create_test_request(
        "files/",
        data=QueryDict("object=cni,JECT 2&results=filename,object&sort=filename"),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 3

        for i in range(2, len(public_test_rows)):
            assert len(response.data["results"][i - 2].keys()) == 3
            assert "id" in response.data["results"][i - 2]
            assert response.data["results"][i - 2]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i - 2]["object"] == public_test_rows[i].object
            )


@basic_django_setup
def test_instrument_filter():
    """Test adding an instrument filter"""

    request = create_test_request(
        "files/",
        data=QueryDict(
            "object=eq,object 2&filters=instrument,SHARCS&results=filename,object&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == os.path.basename(
            public_test_rows[4].filename
        )
        assert response.data["results"][0]["object"] == public_test_rows[4].object


@basic_django_setup
def test_coord_filter():
    """Test a coord filter"""
    # This cannot actually run the query, because the mock sqllite database doesn't handle coordiante searches. We can still
    # test that the filter is added

    from astropy.coordinates import Angle
    from lick_archive.apps.query.views import QuerySerializer
    from lick_archive.config.archive_config import ArchiveConfigFile

    lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

    # Test with specific radius
    request = create_test_request(
        "files/", data=QueryDict("coord=in,349.99,-5.1656,0.1")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        filter_backend = view.filter_backends[0]()
        queryset = view.get_queryset()

        # Build validated_query field in request expected by QueryAPIFilterBackend
        serializer = QuerySerializer(data=request.query_params, view=view)
        serializer.is_valid(raise_exception=True)
        request.validated_query = serializer.validated_data
        queryset = filter_backend.filter_queryset(
            request=request, queryset=queryset, view=view
        )
        # Dig into the SQLAlchemy stuff to validate the filter
        assert queryset.where_filters[0].left.name == "coord"
        queryset.where_filters[0].operator.opstring == "<@"
        assert queryset.where_filters[0].right.value.ra == Angle("349.99 deg")
        assert queryset.where_filters[0].right.value.ra.unit == "rad"
        assert queryset.where_filters[0].right.value.dec == ("-5.1656 deg")
        assert queryset.where_filters[0].right.value.dec.unit == "rad"
        assert queryset.where_filters[0].right.value.radius == Angle("0.1 arcsec")
        assert queryset.where_filters[0].right.value.radius.unit == "rad"

    # Test with default radius
    request = create_test_request("files/", data=QueryDict("coord=in,349.99,-5.1656"))

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        filter_backend = view.filter_backends[0]()
        queryset = view.get_queryset()

        # Build validated_query field in request expected by QueryAPIFilterBackend
        serializer = QuerySerializer(data=request.query_params, view=view)
        serializer.is_valid(raise_exception=True)
        request.validated_query = serializer.validated_data

        queryset = filter_backend.filter_queryset(
            request=request, queryset=queryset, view=view
        )
        assert queryset.where_filters[0].left.name == "coord"
        queryset.where_filters[0].operator.opstring == "<@"
        assert queryset.where_filters[0].right.value.ra == Angle("349.99 deg")
        assert queryset.where_filters[0].right.value.ra.unit == "rad"
        assert queryset.where_filters[0].right.value.dec == Angle("-5.1656 deg")
        assert queryset.where_filters[0].right.value.dec.unit == "rad"
        assert queryset.where_filters[0].right.value.radius == Angle(
            lick_archive_config.query.default_search_radius
        )
        assert queryset.where_filters[0].right.value.radius.unit == "rad"


@basic_django_setup
def test_date_filter():
    """Test a date filter"""

    request = create_test_request(
        "files/", data=QueryDict("obs_date=eq,2018-12-1&results=filename,obs_date")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile2.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2018, month=12, day=1
        )

        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile2.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2018, month=12, day=1
        )


@basic_django_setup
def test_date_range_filter():
    """Test a date range filter"""

    request = create_test_request(
        "files/",
        data=QueryDict(
            "obs_date=in,2018-12-31,2020-01-01&results=filename,obs_date&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 2

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile1.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2019, month=6, day=1
        )

        assert len(response.data["results"][1].keys()) == 3
        assert "id" in response.data["results"][1]
        assert response.data["results"][1]["filename"] == "testfile3.fits"
        assert response.data["results"][1]["obs_date"] == datetime(
            year=2019, month=6, day=1
        )


@basic_django_setup
def test_reverse_date_range_filter():
    """Test that a reversed date range is handled correctly"""

    request = create_test_request(
        "files/",
        data=QueryDict(
            "obs_date=in,2020-01-01,2018-12-31&results=filename,obs_date&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 2

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile1.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2019, month=6, day=1
        )

        assert len(response.data["results"][1].keys()) == 3
        assert "id" in response.data["results"][1]
        assert response.data["results"][1]["filename"] == "testfile3.fits"
        assert response.data["results"][1]["obs_date"] == datetime(
            year=2019, month=6, day=1
        )


@basic_django_setup
def test_no_sort_attributes():
    """Test a query with no specified sort attributes. The results should be sorted by id"""

    request = create_test_request(
        "files/", data=QueryDict("filename=sw,testfile&results=filename,obs_date")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == len(public_test_rows)

        # In this test we don't care about the specific order, only that the ids are in order
        for result in response.data["results"]:

            assert len(result.keys()) == 3
            assert "id" in result

        assert (
            response.data["results"][0]["id"]
            < response.data["results"][1]["id"]
            < response.data["results"][2]["id"]
            < response.data["results"][3]["id"]
        )


@basic_django_setup
def test_no_result_attributes():
    """Test a query with no specified result attributes. This should return all allowed result attributes (and id)
    This also tests the header field post-processing
    """

    request = create_test_request(
        "files/", data=QueryDict("filename=sw,testfile&sort=filename")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == len(public_test_rows)

        for i in range(len(public_test_rows)):
            assert "id" in response.data["results"][i]
            assert response.data["results"][i]["filename"] == os.path.basename(
                public_test_rows[i].filename
            )
            assert (
                response.data["results"][i]["obs_date"] == public_test_rows[i].obs_date
            )
            if "object" not in response.data["results"][i]:
                # One row has a NULL object that won't show up in the results
                assert response.data["results"][i]["filename"] == "testfile1.fits"
            else:
                assert (
                    response.data["results"][i]["object"] == public_test_rows[i].object
                )
            # The frame type is converted from a python enum to a string
            assert (
                response.data["results"][i]["frame_type"]
                == public_test_rows[i].frame_type.name
            )

            # Post-processing by the view should turn the header into a URL
            assert response.data["results"][i][
                "header"
            ] == "http://testserver/archive/data/{}/header".format(
                os.path.basename(public_test_rows[i].filename)
            )

            # Post-processing by the view should include a download URL
            assert response.data["results"][i][
                "download_link"
            ] == "http://testserver/archive/data/{}".format(
                os.path.basename(public_test_rows[i].filename)
            )


@basic_django_setup
def test_count():
    """Test a count query"""

    request = create_test_request(
        "files/", data=QueryDict("obs_date=eq,2019-06-01&count=t")
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)
        assert response.data["count"] == 2


@basic_django_setup
def test_invalid_query():

    request = create_test_request(
        "files/", data=QueryDict("filename=eq,file.fits&results=invalid_field")
    )
    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)

        with pytest.raises(ValidationError):
            view.list(request)


@basic_django_setup
def test_multiple_field_query():

    # Object and date
    request = create_test_request(
        "files/",
        data=QueryDict(
            "obs_date=in,2018-01-01,2020-01-01&object=eq,object 2&results=filename,obs_date&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile3.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2019, month=6, day=1
        )

    # Object, date, filename
    request = create_test_request(
        "files/",
        data=QueryDict(
            "obs_date=in,2020-01-01,2023-01-01&object=eq,object 2&filename=sw,testfile&results=filename,obs_date&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 2

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile4.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2020, month=6, day=1
        )

        assert len(response.data["results"][1].keys()) == 3
        assert "id" in response.data["results"][1]
        assert response.data["results"][1]["filename"] == "testfile5.fits"
        assert response.data["results"][1]["obs_date"] == datetime(
            year=2022, month=6, day=1
        )

    # object, date, filename + instrument filter

    request = create_test_request(
        "files/",
        data=QueryDict(
            "obs_date=in,2020-01-01,2023-01-01&object=eq,object 2&filename=sw,testfile&filters=instrument,SHARCS&results=filename,obs_date&sort=filename"
        ),
    )

    with MockDatabase(Base, test_rows) as mock_db:
        view = create_mock_view(mock_db.engine, request)
        response = view.list(request)

        assert len(response.data["results"]) == 1

        assert len(response.data["results"][0].keys()) == 3
        assert "id" in response.data["results"][0]
        assert response.data["results"][0]["filename"] == "testfile5.fits"
        assert response.data["results"][0]["obs_date"] == datetime(
            year=2022, month=6, day=1
        )
