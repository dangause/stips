from collections import namedtuple
from datetime import date
from urllib.parse import quote

import pytest
from astropy import units
from astropy.coordinates import Angle, SkyCoord
from test_utils import basic_django_setup


@basic_django_setup
def test_query_serializer(archive_config):

    MockView = namedtuple(
        "MockView", ["allowed_result_attributes", "allowed_sort_attributes"]
    )
    mock_view = MockView(
        allowed_result_attributes=[
            "filename",
            "obs_date",
            "object",
            "frame_type",
            "header",
        ],
        allowed_sort_attributes=["id", "filename", "object", "obs_date"],
    )

    from django.http import QueryDict
    from lick_archive.apps.query.views import QuerySerializer
    from rest_framework.serializers import ValidationError

    # filename query
    query_params = QueryDict(
        "filename=eq,afile.fits&results=filename,obs_date,frame_type,object"
    )

    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["filename"] == ["eq", "afile.fits"]
    assert serializer.validated_data["results"] == [
        "filename",
        "obs_date",
        "frame_type",
        "object",
    ]
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "coord" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # filename "in" query
    query_params = QueryDict(
        "filename=in,afile.fits,anotherfile.fits&results=filename,obs_date,frame_type,object"
    )

    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["filename"] == [
        "in",
        "afile.fits",
        "anotherfile.fits",
    ]
    assert serializer.validated_data["results"] == [
        "filename",
        "obs_date",
        "frame_type",
        "object",
    ]
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "coord" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # Date query
    query_params = QueryDict("obs_date=eq,1970-01-01")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["obs_date"] == [
        "eq",
        date(year=1970, month=1, day=1),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "coord" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # Date range with count, filter, and sort
    query_params = QueryDict(
        "obs_date=in,1970-01-01,2023-01-01&filters=instrument,SHARCS,KAST_RED&count=t&sort=filename"
    )
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["obs_date"] == [
        "in",
        date(year=1970, month=1, day=1),
        date(year=2023, month=1, day=1),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["filename"]
    assert serializer.validated_data["count"] is True
    assert "ShaneAO/ShARCS" in serializer.validated_data["filters"]
    assert "Kast Red" in serializer.validated_data["filters"]
    assert len(serializer.validated_data["filters"]) == 2
    assert "filename" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "coord" not in serializer.validated_data

    # Object query with prefix and sort
    query_params = QueryDict("object=sw,HD3&sort=object,-obs_date")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["object"] == ["sw", "HD3"]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["object", "-obs_date"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "coord" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # Everything empty
    query_params = QueryDict("")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "coord" not in serializer.validated_data
    assert "filters" not in serializer.validated_data
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False

    # Invalid dates
    query_params = QueryDict("obs_date=eq,1970-13-56")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Date has the wrong format"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("obs_date=in,01/01/1970,01/01/2023")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Date has the wrong format"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("obs_date=in,1970-01-01,1980-01-01,1990-01-01")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Too many values specified"):
        serializer.is_valid(raise_exception=True)

    # Invalid operator
    query_params = QueryDict("filename=cn,afile.fits")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Unsupported operator."):
        serializer.is_valid(raise_exception=True)

    # Invalid results (fails regex)
    query_params = QueryDict("results=99,38")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(
        ValidationError, match="This value does not match the required pattern."
    ):
        serializer.is_valid(raise_exception=True)

    # Invalid result (not in allowed list)
    query_params = QueryDict("results=filename,coord")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="coord is not a valid result field."):
        serializer.is_valid(raise_exception=True)

    # Invalid sort (fails regex)
    query_params = QueryDict("sort=99")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(
        ValidationError, match="This value does not match the required pattern."
    ):
        serializer.is_valid(raise_exception=True)

    # Another invalid sort. We have to quote the + or it get ignored by the QueryDict
    query_params = QueryDict("sort=" + quote("+-id"))
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(
        ValidationError, match="This value does not match the required pattern."
    ):
        serializer.is_valid(raise_exception=True)

    # Invalid sort (not in allowed list)
    query_params = QueryDict("sort=object,-frame_type,header")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError) as exc_info:
        serializer.is_valid(raise_exception=True)

    assert (
        exc_info.value.detail["sort"][0]["sort"]
        == "frame_type is not a valid field for sorting"
    )
    assert (
        exc_info.value.detail["sort"][1]["sort"]
        == "header is not a valid field for sorting"
    )


def test_coord_validation(archive_config):

    MockView = namedtuple(
        "MockView", ["allowed_result_attributes", "allowed_sort_attributes"]
    )
    mock_view = MockView(
        allowed_result_attributes=[
            "filename",
            "obs_date",
            "object",
            "frame_type",
            "header",
        ],
        allowed_sort_attributes=["id", "filename", "object", "obs_date"],
    )

    from django.http import QueryDict
    from lick_archive.apps.query.views import QuerySerializer
    from rest_framework.serializers import ValidationError

    # coord query, decimal degrees, with no radius, + on sort. Note + must be quoted
    query_params = QueryDict("coord=in,349.99,-5.1656&sort=" + quote("+obs_date"))
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["coord"] == [
        "in",
        (
            SkyCoord(Angle(349.99, unit=units.deg), Angle(-5.1656, unit=units.deg)),
            Angle(archive_config.query.default_search_radius),
        ),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["+obs_date"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # coord query, decimal degrees, with radius
    query_params = QueryDict("coord=in,349.99,-5.1656,0.1&sort=obs_date")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["coord"] == [
        "in",
        (
            SkyCoord(Angle(349.99, unit=units.deg), Angle(-5.1656, unit=units.deg)),
            Angle(0.1, unit=units.arcsec),
        ),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["obs_date"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # decimal with units
    query_params = QueryDict("coord=in,12h,-5.1656,0.1&sort=obs_date")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["coord"] == [
        "in",
        (
            SkyCoord(Angle(12, unit=units.hourangle), Angle(-5.1656, unit=units.deg)),
            Angle(0.1, unit=units.arcsec),
        ),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["obs_date"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # sexagesimal with units on the radius
    query_params = QueryDict("coord=in,12:30:30,-0:10:5.1656,1m")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["coord"] == [
        "in",
        (
            SkyCoord(
                Angle("12:30:30", unit=units.hourangle),
                Angle("-0:10:5.1656", unit=units.deg),
            ),
            Angle("1", unit=units.arcmin),
        ),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # sexagesimal with units
    query_params = QueryDict("coord=in,180d 30m 30s,-0d 10m 5.1656s,1m")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    assert serializer.is_valid(raise_exception=True) is True
    assert serializer.validated_data["coord"] == [
        "in",
        (
            SkyCoord(
                Angle("180:30:30", unit=units.deg),
                Angle("-0:10:5.1656", unit=units.deg),
            ),
            Angle("1", unit=units.arcmin),
        ),
    ]
    assert serializer.validated_data["results"] == []
    assert serializer.validated_data["sort"] == ["id"]
    assert serializer.validated_data["count"] is False
    assert "filename" not in serializer.validated_data
    assert "obs_date" not in serializer.validated_data
    assert "object" not in serializer.validated_data
    assert "filters" not in serializer.validated_data

    # Invalid coord
    query_params = QueryDict("coord=in,100,-91")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="DEC must be between"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,91")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="DEC must be between"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=eq,100,-89")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Unsupported operator"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(
        ValidationError, match="Coordinate value should consist of ra, dec"
    ):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89,2,1")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(
        ValidationError, match="Coordinate value should consist of ra, dec"
    ):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100:,-89,2")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for RA"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89:,2")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for DEC"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89,a")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Radius has invalid character"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89,h")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for Radius"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89,-2s")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Radius must be >0"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100,-89,0d")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Radius must be >0"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,10:62:00,-89")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for RA"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,100:50:00,-89:62:00")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for RA"):
        serializer.is_valid(raise_exception=True)

    query_params = QueryDict("coord=in,10:50:00,-89:62:00")
    serializer = QuerySerializer(data=query_params, view=mock_view)
    with pytest.raises(ValidationError, match="Invalid angle specified for DEC"):
        serializer.is_valid(raise_exception=True)
