"""Tests the interface between the SQLAlchemy ORM and Django."""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from astropy.coordinates import Angle, SkyCoord
from django.db.models import F, Value
from lick_archive.apps.query.sqlalchemy_django_utils import (
    SQLAlchemyORMSerializer,
    SQLAlchemyQuerySet,
)
from lick_archive.db.archive_schema import Base, FileMetadata, UserDataAccess
from lick_archive.db.pgsphere import SCircle
from lick_archive.metadata.data_dictionary import FrameType, Instrument, Telescope
from lick_archive.metadata.metadata_utils import get_hdul_from_text
from lick_archive.metadata.shane_ao_sharcs import ShaneAO_ShARCS
from rest_framework.exceptions import APIException
from rest_framework.serializers import ValidationError
from test_utils import MockDatabase


def test_sqlalchemy_orm_serializer():

    # Create a test FileMetadata object from unit test data
    test_data_dir = Path(__file__).parent / "test_data"

    file = "2014-05_20_AO_s0002-hdu0.txt"
    hdul = get_hdul_from_text([test_data_dir / file])
    path = Path(file.replace("_", os.sep).replace(".txt", ".fits"))
    reader = ShaneAO_ShARCS()
    row = reader.read_row(path, hdul)
    row_mapping = {
        col.name: getattr(row, col.name)
        for col in row.__table__.columns
        if col.name not in ["header", "coord"]
    }

    serializer = SQLAlchemyORMSerializer()
    result = serializer.to_representation(row_mapping)
    # Test an SQL Alchemy enum
    assert result["telescope"] == Telescope.SHANE.value
    # Test datetime
    assert result["obs_date"] == datetime(
        2014, 5, 20, 22, 49, 25, 515000, tzinfo=timezone.utc
    )
    # Test float
    assert result["exptime"] == 0.9797
    # Test string
    assert result["object"] == "domeflats"
    # Test Python enum
    assert result["frame_type"] == "flat"
    # Test bitstring
    assert result["ingest_flags"] == "00000000000000000000000000000110"

    with pytest.raises(ValueError, match="Error serializing database results."):
        serializer.to_representation(row)


def test_queryset_get_orm_attrib():
    queryset = SQLAlchemyQuerySet(None, FileMetadata)

    # Valid attribute
    joins, orm_attr = queryset._get_orm_attrib("obs_date", "results")
    assert orm_attr == FileMetadata.obs_date
    assert len(joins) == 0

    # Joined attribute
    joins, orm_attr = queryset._get_orm_attrib("user_access.obid", "results")
    assert orm_attr == UserDataAccess.obid
    assert len(joins) == 1
    assert list(joins)[0] is FileMetadata.user_access

    # Invalid attribute
    with pytest.raises(ValidationError) as exc_info:
        queryset._get_orm_attrib("not_real_attrib", "results")
    assert "Unknown field not_real_attrib" in exc_info.value.detail["results"]


def test_queryset_filter():

    test_rows = [
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.arc,
            object=None,
            filename="testfile1.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="object 1",
            filename="testfile2.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="object 2",
            filename="testfile3.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="object 3",
            filename="testfile4.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        queryset = SQLAlchemyQuerySet(mock_db.engine, FileMetadata)

        # Cover "exact" and "range"
        filtered_queryset = queryset.filter(
            frame_type__exact=FrameType.science,
            obs_date__range=(
                datetime(year=2019, month=1, day=1, hour=0, minute=0, second=0),
                datetime(year=2019, month=12, day=31, hour=23, minute=59, second=59),
            ),
        )

        for row in filtered_queryset:
            assert row.filename == "testfile3.fits"

        # Cover "startswith", "lt", and "gt"
        filtered_queryset = queryset.filter(
            object__startswith="object",
            obs_date__gt=datetime(
                year=2018, month=1, day=1, hour=0, minute=0, second=0
            ),
            obs_date__lt=datetime(
                year=2020, month=1, day=1, hour=0, minute=0, second=0
            ),
        )

        for row in filtered_queryset:
            assert row.filename in ["testfile2.fits", "testfile3.fits"]

        # Cover is NULL/None
        filtered_queryset = queryset.filter(object__exact=None)

        assert filtered_queryset[0].filename == "testfile1.fits"

        # No results
        filtered_queryset = queryset.filter(object__exact="Not a real object")
        with pytest.raises(IndexError):
            filtered_queryset[0].object == "Not a real object"

        # Test coord search, but we can't actually run this query against sqllite
        filtered_queryset = queryset.filter(
            coord__contained_in=SCircle(
                SkyCoord(ra="20 deg", dec="20 deg"), Angle("0.5 deg")
            )
        )

        # Test error cases
        with pytest.raises(APIException, match="Failed building query."):
            # Missing one Underscore
            filtered_queryset = queryset.filter(object_startswith="object")

        with pytest.raises(APIException, match="Failed building query."):
            # Unsupported op
            filtered_queryset = queryset.filter(
                ingest_flags__and="00000000000000000000000000000001"
            )

        with pytest.raises(APIException, match="Unknown field bad_field."):
            # Unknown field
            filtered_queryset = queryset.filter(bad_field__exact=3)


def test_queryset_order_by():

    test_rows = [
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.arc,
            object="Object C",
            filename="testfile1.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object D",
            filename="testfile2.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object B",
            filename="testfile3.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object A",
            filename="testfile4.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        queryset = SQLAlchemyQuerySet(mock_db.engine, FileMetadata)

        # Cover ascending sort
        filtered_queryset = queryset.order_by(["object"])

        assert filtered_queryset[0].object == "Object A"
        assert filtered_queryset[1].object == "Object B"
        assert filtered_queryset[2].object == "Object C"
        assert filtered_queryset[3].object == "Object D"

        # Cover descending sort
        filtered_queryset = queryset.order_by(["-object"])

        assert filtered_queryset[0].object == "Object D"
        assert filtered_queryset[1].object == "Object C"
        assert filtered_queryset[2].object == "Object B"
        assert filtered_queryset[3].object == "Object A"


def test_queryset_values():

    test_rows = [
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.arc,
            object="Object C",
            filename="testfile1.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object D",
            filename="testfile2.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object B",
            filename="testfile3.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object A",
            filename="testfile4.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        queryset = SQLAlchemyQuerySet(mock_db.engine, FileMetadata)

        # Values should return mapping values, with the filename subsittued in for "test_ref"
        # We also sort by object so we can be sure of the order
        filtered_queryset = queryset.values(
            "filename", "object", test_ref=F("filename")
        ).order_by("object")

        assert filtered_queryset[0]["object"] == "Object A"
        assert filtered_queryset[1]["object"] == "Object B"
        assert filtered_queryset[2]["object"] == "Object C"
        assert filtered_queryset[3]["object"] == "Object D"

        assert filtered_queryset[0]["test_ref"] == "testfile4.fits"
        assert filtered_queryset[1]["test_ref"] == "testfile3.fits"
        assert filtered_queryset[2]["test_ref"] == "testfile1.fits"
        assert filtered_queryset[3]["test_ref"] == "testfile2.fits"

        # Test an unsupported expression
        with pytest.raises(APIException, match="Internal error processing results"):
            filtered_queryset = queryset.values(
                "filename", "object", test_ref=Value("Test Prefix") + F("filename")
            )


def test_queryset_slicing():
    test_rows = [
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.arc,
            object="Object C",
            filename="testfile1.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object D",
            filename="testfile2.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object B",
            filename="testfile3.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object A",
            filename="testfile4.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        queryset = SQLAlchemyQuerySet(mock_db.engine, FileMetadata)

        # Test with entire ORM objects
        queryset_sorted = queryset.order_by("object")
        results = queryset_sorted[1:3]

        assert results[0].object == "Object B"
        assert results[1].object == "Object C"

        # Should only have pulled 2 results
        with pytest.raises(IndexError):
            assert results[2].object == "Object D"

        # Test partial slices
        results = queryset_sorted[:3]
        assert results[0].object == "Object A"
        assert results[1].object == "Object B"
        assert results[2].object == "Object C"

        # Should only have pulled 3 results
        with pytest.raises(IndexError):
            assert results[3].object == "Object D"

        results = queryset_sorted[1:]
        assert results[0].object == "Object B"
        assert results[1].object == "Object C"
        assert results[2].object == "Object D"

        # Should only have pulled 3 results
        with pytest.raises(IndexError):
            assert results[3].object == "Object E"

        results = queryset_sorted[:]
        assert results[0].object == "Object A"
        assert results[1].object == "Object B"
        assert results[2].object == "Object C"
        assert results[3].object == "Object D"

        # Test with mappings
        queryset_sorted = queryset.order_by("object").values("object")
        results = queryset_sorted[1:3]

        assert results[0]["object"] == "Object B"
        assert results[1]["object"] == "Object C"

        # Should only have pulled 2 results
        with pytest.raises(IndexError):
            assert results[2]["object"] == "Object D"

        # Test partial slices
        results = queryset_sorted[:3]
        assert results[0]["object"] == "Object A"
        assert results[1]["object"] == "Object B"
        assert results[2]["object"] == "Object C"

        # Should only have pulled 3 results
        with pytest.raises(IndexError):
            assert results[3]["object"] == "Object D"

        results = queryset_sorted[1:]
        assert results[0]["object"] == "Object B"
        assert results[1]["object"] == "Object C"
        assert results[2]["object"] == "Object D"

        # Should only have pulled 3 results
        with pytest.raises(IndexError):
            assert results[3]["object"] == "Object E"

        results = queryset_sorted[:]
        assert results[0]["object"] == "Object A"
        assert results[1]["object"] == "Object B"
        assert results[2]["object"] == "Object C"
        assert results[3]["object"] == "Object D"

        # Test everything with no filters/sorts/results
        results = list(queryset[:])
        assert len(results) == 4
        for result in results:
            assert result.filename in [
                "testfile1.fits",
                "testfile2.fits",
                "testfile3.fits",
                "testfile4.fits",
            ]

        # Test with unsupported step
        with pytest.raises(
            APIException, match="Failed to build query archive database."
        ):
            queryset_sorted = queryset.order_by("object")[1:3:2]


def test_queryset_count():
    test_rows = [
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.arc,
            object="Object C",
            filename="testfile1.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2018, month=12, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object D",
            filename="testfile2.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2019, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object B",
            filename="testfile3.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
        FileMetadata(
            telescope=Telescope.SHANE,
            instrument=Instrument.KAST_BLUE,
            obs_date=datetime(year=2020, month=6, day=1, hour=0, minute=0, second=0),
            frame_type=FrameType.science,
            object="Object A",
            filename="testfile4.fits",
            ingest_flags="00000000000000000000000000000000",
        ),
    ]

    with MockDatabase(Base, test_rows) as mock_db:
        queryset = SQLAlchemyQuerySet(mock_db.engine, FileMetadata)

        # Test total count
        assert queryset.count() == 4

        # Test filtered count
        assert queryset.filter(frame_type__exact=FrameType.science).count() == 3

        # Test zero count
        assert queryset.filter(frame_type__exact=FrameType.flat).count() == 0
