"""The views that make up the lick archive query app."""

import logging

logger = logging.getLogger(__name__)

from pathlib import Path

from astropy import units
from astropy.coordinates import Angle
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.archive_schema import FileMetadata
from lick_archive.db.db_utils import create_db_engine
from lick_archive.metadata.data_dictionary import api_capabilities
from lick_archive.utils.django_utils import log_request_debug
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.renderers import BaseRenderer
from rest_framework.serializers import BaseSerializer

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config

from .query_api import (
    QueryAPIFilterBackend,
    QueryAPIPagination,
    QueryAPIView,
    QuerySerializer,
)
from .sqlalchemy_django_utils import SQLAlchemyORMSerializer

# SQLAlchemy likes its engine to have a global lifetime.
_db_engine = create_db_engine(
    user=lick_archive_config.database.db_query_user,
    database=lick_archive_config.database.archive_db,
)


class QueryView(QueryAPIView, ListAPIView):
    """View that integrates the archive Query API with SQL Alchemy"""

    pagination_class = QueryAPIPagination
    filter_backends = [QueryAPIFilterBackend]
    serializer_class = SQLAlchemyORMSerializer
    required_attributes = list(api_capabilities["required"]["db_name"])
    allowed_sort_attributes = list(api_capabilities["sort"]["db_name"])
    allowed_result_attributes = list(api_capabilities["result"]["db_name"])

    def __init__(self):
        super().__init__(_db_engine, FileMetadata)

    def list(self, request, *args, **kwargs):
        """Performs a query based on a request. The query is handled by the
        QueryAPIPagination, and QueryAPIFilterBackend classes.
        This class performs post processing of database results.

        The post processing involves:
        Replacing the full path in the filename to the relative path. (Hiding the
        mount point of the archive file system from clients).

        Replacing the filename returned as "header" with a URL that can be used to
        access a plaintext version of the header.

        Args:
        request (rest_framework.requests.Request): The request specifying the query.
        args (list):     Additional arguments to the view.
        **kwargs (dict): Additional keyword arguments to the view.

        Return (rest_framework.response.Response): The processed response from the query.
        """
        log_request_debug(request)

        # Validate the query using a serializer
        serializer = QuerySerializer(data=request.query_params, view=self)
        logger.debug(f"QueryParams {request.query_params}")
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            logger.error(f"QueryParams {request.query_params}", exc_info=True)
            raise

        # Store the validated results in the request to be passed to paginators and filters
        request.validated_query = serializer.validated_data

        # Use the superclass method to utilize the DRF's infrastructure
        response = super().list(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            # A count query doesn't have a results entry
            if "results" in response.data:

                coord_format = request.validated_query.get("coord_format", "asis")

                # Filter header URLS to have the propper format,
                # to make filename a relative path, and to make header download_link
                # URLs.
                for record in response.data["results"]:
                    if "header" in record:
                        filepath = Path(record["header"])
                        relative_path = filepath.relative_to(
                            lick_archive_config.ingest.archive_root_dir
                        )
                        header_url = (
                            lick_archive_config.query.file_header_url_format.format(
                                relative_path
                            )
                        )
                        record["header"] = header_url
                    if "filename" in record:
                        record["filename"] = str(
                            Path(record["filename"]).relative_to(
                                lick_archive_config.ingest.archive_root_dir
                            )
                        )
                    if "download_link" in record:
                        filepath = Path(record["download_link"])
                        relative_path = filepath.relative_to(
                            lick_archive_config.ingest.archive_root_dir
                        )
                        download_url = lick_archive_config.download.file_download_url_format.format(
                            relative_path
                        )
                        record["download_link"] = download_url
                    if coord_format != "asis":
                        if "ra" in record:
                            record["ra"] = self._convertAngle(
                                record["ra"], coord_format, hour_angle=True
                            )
                        if "dec" in record:
                            record["dec"] = self._convertAngle(
                                record["dec"], coord_format, hour_angle=False
                            )
        return response

    def _convertAngle(
        self, angle_value: str, coord_format: str, hour_angle: bool = False
    ):
        """Convert a returned angle value to the requested format.

        Args:
            angle_value: The angle value from the database (originally from the FITS header)
            coord_format: The requested format, one of "hmsdms" or "degrees".
            hour_angle:  True if this value should be treated as an hour angle, False if should be treated as degrees. Only applicable if the coord_format is "hmsdms".

        Return Value:
            The converted angle value.
        """
        # First see if the value can be treated as floating point, if so treat it as decimal degreees
        try:
            value = float(angle_value)
            angle = Angle(value, unit=units.deg)
        except Exception:
            # Next try to treat it as sexagesimal
            try:
                if any([c in "hdms" for c in angle_value.lower()]):
                    # There are explicit units
                    angle = Angle(angle_value)
                elif hour_angle:
                    angle = Angle(angle_value, unit=units.hourangle)
                else:
                    angle = Angle(angle_value, unit=units.deg)
            except Exception:
                logger.error(
                    f"Could not convert angle value {angle_value}, leaving asis"
                )
                return angle_value

        # Use astropy the convert to the desired format
        if hour_angle and coord_format == "hmsdms":
            output_unit = units.hourangle
        else:
            output_unit = units.deg

        if coord_format == "hmsdms":
            return angle.to_string(
                unit=output_unit, decimal=False, precision=2, sep=":"
            )
        else:
            return angle.to_string(unit=output_unit, decimal=True, precision=8)


class PlainTextRenderer(BaseRenderer):
    """A renderer for rendering FITS headers in plain text."""

    media_type = "text_plain"
    format = "txt"
    charset = "ascii"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Return the plain text if the response is successfull.
        # Otherwise return the status code, reason phrase, and error message returned in the data
        if renderer_context is not None and "response" in renderer_context:
            response = renderer_context["response"]
            if response.status_code == status.HTTP_200_OK:
                return data + "\n" if data[-1] != "\n" else data
            elif isinstance(data, dict) and "detail" in data:
                return f"Status Code: {response.status_code}: {response.reason_phrase}\n\n{data['detail']}\n"
            else:
                return (
                    f"Status Code: {response.status_code}: {response.reason_phrase}\n"
                )
        # If we can't get the response, give up let the django/drf deal with it
        else:
            raise APIException(
                detail="Internal Error", code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HeaderSerializer(BaseSerializer):
    """Serialize a metadata row by returning its header"""

    def to_representation(self, instance):
        return instance.header


class HeaderView(QueryAPIView, RetrieveAPIView):
    """A view for getting the header for a specific fits file in the archive."""

    renderer_classes = [PlainTextRenderer]
    filter_backends = [QueryAPIFilterBackend]
    serializer_class = HeaderSerializer
    lookup_url_kwarg = "file"
    lookup_field = "filename"
    required_attributes = ["filename"]
    allowed_result_attributes = ["header"]
    allowed_sort_attributes = ["id"]

    def __init__(self):
        super().__init__(_db_engine, FileMetadata)
