import logging

logger = logging.getLogger(__name__)

import datetime
import os

from django.db.models import F, Q
from lick_archive.authorization.date_utils import get_observing_night
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.db.pgsphere import SCircle
from lick_archive.metadata.data_dictionary import (
    MAX_FILENAME_BATCH,
    MAX_FILENAME_SIZE,
    MAX_OBJECT_SIZE,
    Instrument,
)
from lick_archive.utils.django_utils import log_request_debug
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .fields import CoordField, ISODateOrDateTimeField, ListWithSeperator, QueryField
from .sqlalchemy_django_utils import SQLAlchemyQuerySet

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


"""The classes that implement the query API used by the lick archive."""


class QuerySerializer(serializers.Serializer):
    """A Serializer class used to validate the query string."""

    filename = QueryField(
        operators=["eq", "sw", "in"],
        value=serializers.CharField(max_length=MAX_FILENAME_SIZE),
        allow_empty=True,
        split_values=True,
        max_value_length=MAX_FILENAME_SIZE,
        max_num_values=MAX_FILENAME_BATCH,
        required=False,
    )

    obs_date = QueryField(
        operators=["eq", "in"],
        value=ISODateOrDateTimeField(),
        max_num_values=2,
        split_values=True,
        max_value_length=len("9999-99-99T99:99:99.99999"),
        required=False,
    )

    object = QueryField(
        operators=["eq", "sw", "cn", "eqi", "swi", "cni"],
        value=serializers.CharField(max_length=MAX_OBJECT_SIZE),
        max_value_length=MAX_OBJECT_SIZE,
        required=False,
    )

    coord = QueryField(
        operators=["in"],
        value=CoordField(
            default_radius=lick_archive_config.query.default_search_radius
        ),
        required=False,
    )
    coord_format = serializers.ChoiceField(
        default="asis", choices=["asis", "hmsdms", "degrees"], required=False
    )
    count = serializers.BooleanField(default=False, required=False)
    results = ListWithSeperator(
        sep_char=",",
        child=serializers.RegexField(
            regex=r"^[A-Za-z][A-Za-z0-9_]*$", max_length=30, allow_blank=False
        ),
        default=[],
        max_length=128,
    )
    sort = ListWithSeperator(
        sep_char=",",
        child=serializers.RegexField(
            regex=r"^(-|\+)?[A-Za-z][A-Za-z0-9_]*$", max_length=30, allow_blank=False
        ),
        default=["id"],
        max_length=128,
        required=False,
        allow_empty=False,
    )
    filters = ListWithSeperator(
        sep_char=",",
        child=serializers.CharField(max_length=60, allow_blank=False),
        min_length=1,
        max_length=128,
        required=False,
        allow_empty=False,
    )

    def __init__(self, data, view):
        """
        Initialize the serializer.

        Args:
        data (django.http.QueryDict): The QueryDict representing the query string as parsed by Django.
        view (QueryAPIView):          The view object receiving the query.
                                      It should specify allowed_result_attributes, and allowed_sort_attributes
                                      as attributes.
        """
        self.allowed_result_attributes = view.allowed_result_attributes
        self.allowed_sort_attributes = view.allowed_sort_attributes

        super().__init__(data=data)

    def validate_filters(self, value):
        """Validate the filters passed into the query."""
        # Eventually this might allow filtering on arbitrary fields using simple expressions,
        # but for now we only allow one filter, on instrument
        if value[0] != "instrument":
            raise serializers.ValidationError(
                [{"filters": 'Only "instrument" is allowed as a filter.'}]
            )
        requested_instruments = []
        valid_instruments = [x.name for x in Instrument]
        for instrument in value[1:]:
            # We'll allow case insensitive instrument names in the query
            if instrument.upper() in valid_instruments:
                # The DB holds the string value of the enum
                requested_instruments.append(Instrument[instrument.upper()].value)
            else:
                raise serializers.ValidationError(
                    [
                        {
                            "filters": "Instrument filter must be one of: "
                            + ",".join([f'"{x}"' for x in valid_instruments])
                        }
                    ]
                )
        if len(requested_instruments) == 0:
            raise serializers.ValidationError(
                [
                    {
                        "filters": "Instrument filter must be one of: "
                        + ",".join([f'"{x}"' for x in valid_instruments])
                    }
                ]
            )
        return requested_instruments

    def validate_sort(self, value):
        """Validate the sort fields of a query"""
        errors = []

        # Validate each field
        for sort_field in value:
            # Pull off the "-" indicating a reversed sort
            if sort_field.startswith("-"):
                field_name = sort_field.strip("-")
            elif sort_field.startswith("+"):
                field_name = sort_field.strip("+")
            else:
                field_name = sort_field

            if field_name not in self.allowed_sort_attributes:
                errors.append(
                    {"sort": f"{field_name} is not a valid field for sorting"}
                )

        if len(errors) > 0:
            raise serializers.ValidationError(errors)
        return value

    def validate_results(self, value):
        """Validate the result fields of a query"""
        errors = []
        for result_field in value:
            if result_field not in self.allowed_result_attributes:
                errors.append(
                    {"results": f"{result_field} is not a valid result field."}
                )

        if len(errors) > 0:
            raise serializers.ValidationError(errors)
        return value

    def validate_obs_date(self, value):
        if value[0] == "in":
            # A "between" query, there should be two values
            if len(value) != 3:
                raise serializers.ValidationError(
                    {
                        "obs_date": 'Date query with "in" did not have a start and an end date.'
                    }
                )
        elif len(value) != 2:
            raise serializers.ValidationError(
                {"obs_date": 'Date query with "eq" did not have one date.'}
            )
        return value


class QueryAPIPagination(PageNumberPagination):
    """Paginate the results of the archive Query API. Uses the Django Rest Framework PageNumberPagination
    class to do most of the work.
    """

    # Define the strings used in the URL to paginate.
    page_size_query_param = "page_size"
    page_size = 50
    max_page_size = 1000

    def __init__(self):
        self.is_count = False

    def paginate_queryset(self, queryset, request, view):
        """Returns the appropriate page of results from a queryset given a request.
        count queries are not paginated.

        Args:
            queryset (django.db.models.query.QuerySet):
            The QuerySet to get results from.

            request (rest_framework.request.Request):
            The request specifying the query.

            view    (QueryAPIView)):
            The view running the query. It should have an allowed_result_attributes attribute.

            Return (Mapping):
            The page the resultsA filtered and sorted QuerySet returning the requested page.
        """

        # Make sure the request has been validated
        if not hasattr(request, "validated_query"):
            logger.error("Unvalidated request passed to paginate_queryset.")
            raise APIException("Unvalidated request passed to paginate_queryset.")

        if request.validated_query["count"] is True:
            # Don't paginate, it's a count query
            # The queryset was already filtered by the view, so just run the count
            self.is_count = True
            return [{"count": queryset.count()}]
        else:
            # Set the result attributes
            logger.info(
                f"QueryParams {request.validated_query} results: {request.validated_query['results']}"
            )

            if len(request.validated_query["results"]) == 0:
                # Use all allowed result attributes if none are set
                requested_attributes = view.allowed_result_attributes
            else:
                requested_attributes = request.validated_query["results"]

                # Make sure all sort attributes are included in the results
                for sort_attribute in request.validated_query["sort"]:
                    if sort_attribute.startswith("+") or sort_attribute.startswith("-"):
                        sort_attribute = sort_attribute[1:]
                    if sort_attribute not in requested_attributes:
                        requested_attributes.append(sort_attribute)

            # Make sure "id" is always in the result attributes
            if "id" not in requested_attributes:
                requested_attributes = ["id"] + requested_attributes

            result_attributes = []
            result_expressions = {}

            # Make a shallow copy of the result attributes, replacing
            # the special "header" and "download_link" attributes with an expression
            # that references the filename
            for api_result_name in requested_attributes:
                if api_result_name in ("header", "download_link"):
                    result_expressions[api_result_name] = F("filename")
                else:
                    result_attributes.append(api_result_name)

            # Apply the result attributes to the queryset
            queryset = queryset.values(*result_attributes, **result_expressions)

        # Use the superclass to handle the logic of paginating
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        """Return a paginated response from data returned from the query.

        Args:
        data (Mapping): A page of data results from a query.

        Return (rest_framework.response.Response):
        The response with the data formatted approriately with next page/previous page links.
        """

        if self.is_count is True:
            # Counts don't need fancy paginated results
            return Response(data[0])
        else:
            return super().get_paginated_response(data)


class QueryAPIFilterBackend:
    """Filter a query set based on a request.

    Args:
        request (rest_framework.request.Request):
        The request specifying the query.

        queryset (django.models.query.QuerySet):
        The queryset to filter.

    view (QueryAPIView):
        The view running the query. It should have the "required_attributes",
        "allowed_sort_attributes" and "allowed_result_attributes" attributes that
        are used to validate the query.

    Return (django.models.query.QuerySet): A QuerySet filtered according to the request.

    Raises:
        rest_framework.serializers.ValidationError: Thrown if the query is not valid.
    """

    def get_ordering(self, request, queryset, view):
        """Return the fields that should be used to order the query based on the
        request.

        Args:
        request (rest_framework.request.Request):
        The request specifying the query.

        queryset (django.models.query.QuerySet):
        The queryset being used for the query.

        view (QueryAPIView):
        The view running the query. It should have the "required_attributes",
        "allowed_sort_attributes" and "allowed_result_attributes" attributes that
        are used to validate the query.

        Return (list): The list of field names to sort by.

        Raises:
        rest_framework.serializers.ValidationError: Thrown if the query is not valid.
        """

        # Make sure the request has been validated
        if not hasattr(request, "validated_query"):
            logger.error("Unvalidated request passed to get_ordering.")
            raise APIException("Unvalidated request passed to get_ordering.")

        return request.validated_query["sort"]

    def filter_queryset(self, request, queryset, view):
        """Filter a query set based on a request.

        Args:
        request (rest_framework.request.Request):
        The request specifying the query.

        queryset (django.models.query.QuerySet):
        The queryset to filter.

        view (QueryAPIView):
        The view running the query. It should have the "required_attributes",
        "allowed_sort_attributes" and "allowed_result_attributes" attributes that
        are used to validate the query.

        Return (django.models.query.QuerySet): A QuerySet filtered according to the request.

        Raises:
        rest_framework.serializers.ValidationError: Thrown if the query is not valid.
        """

        # Make sure the request has been validated
        if not hasattr(request, "validated_query"):
            logger.error("Unvalidated request passed to filter_queryset.")
            raise APIException("Unvalidated request passed to filter_queryset.")

        # Build filtrs for indexed attributes. At least one of these attributes must be specified
        filters = {}
        for field in view.required_attributes:
            if field in request.validated_query:
                operator = request.validated_query[field][0]
                values = request.validated_query[field][1:]
                logger.info(f"Building {field} query {operator} '{values}'")
                self._add_where_filter(filters, field, values, operator)

        if len(filters) == 0:
            raise ValidationError(
                {
                    "query": f"At least one required field must be included in the query. The required fields are: ({', '.join(view.required_attributes)})"
                }
            )

        # Add filters for non-indexed filters. Currently only instrument is supported
        if "filters" in request.validated_query:
            self._build_in_filter(
                filters, "instrument", request.validated_query["filters"]
            )

        # Apply the filters, and then the propreitary access filter
        queryset = queryset.filter(**filters)
        queryset = self._add_proprietary_access_filter(queryset, request)

        # Add sort attributes if needed
        if (
            request.validated_query["count"] is False
            and len(request.validated_query["sort"]) > 0
        ):
            return queryset.order_by(request.validated_query["sort"])
        else:
            return queryset

    def _add_where_filter(self, filters, field, value, operator):
        """Build the Django keyword arguments to filter a queryset.

        Args:
            filters (dict): The current set of filters to add to.

            field (str): The field name to filter on

            value (list): The value or values to filter by.

            operator (str):
                The operator to perform. One of ["eq", "sw", "cn", "eqi", "swi", "cni", "in"]

        """

        # The value will come in as a list, but if there's only one item use it directly
        if len(value) == 1:
            value = value[0]

        if field == "filename":
            # The database has the full filename, but clients only see the relative pathname
            # A weird implication is that if the client can use an absolute path if they want, because
            # os.path.join will ignore the first path if the second path is an absolute path.
            if operator == "in":
                # Value should be a list
                full_filenames = [
                    os.path.join(lick_archive_config.ingest.archive_root_dir, file)
                    for file in value
                ]
                self._build_in_filter(filters, field, full_filenames)
            else:
                full_filename = os.path.join(
                    lick_archive_config.ingest.archive_root_dir, value
                )
                logger.debug(
                    f"rootdir {lick_archive_config.ingest.archive_root_dir}, value {value} Full filename {full_filename}"
                )
                self._build_string_filter(filters, field, full_filename, operator)

        elif field == "object":
            self._build_string_filter(filters, field, value, operator)

        elif field == "obs_date":

            if isinstance(value, list):
                # There are two values, convert to datetimes if needed
                if isinstance(value[0], datetime.datetime):
                    start_date_time = value[0]
                else:
                    start_date_time = datetime.datetime.combine(
                        value[0],
                        datetime.time(hour=0, minute=0, second=0),
                        datetime.timezone.utc,
                    )

                if isinstance(value[1], datetime.datetime):
                    end_date_time = value[1]
                else:
                    end_date_time = datetime.datetime.combine(
                        value[1],
                        datetime.time(
                            hour=23, minute=59, second=59, microsecond=999000
                        ),
                        datetime.timezone.utc,
                    )
            else:
                # There's only one value, if it's a date time, we do an exact match
                if isinstance(value, datetime.datetime):
                    self._build_exact_filter(filters, field, value)
                    return
                else:
                    # There's one date, it must be treated as a range from midnight on that date to
                    # just before midnight on the next
                    start_date_time = datetime.datetime.combine(
                        value,
                        datetime.time(hour=0, minute=0, second=0),
                        datetime.timezone.utc,
                    )
                    end_date_time = start_date_time + datetime.timedelta(
                        hours=23, minutes=59, seconds=59, milliseconds=999
                    )

            self._build_range_filter(
                filters, "obs_date", start_date_time, end_date_time
            )

        elif field == "coord":
            # The QuerySerializer will put the SkyCoord for the query in value[0], and the radius in value[1]
            self._build_contained_in_filter(filters, "coord", value[0], value[1])

        return filters

    def _add_proprietary_access_filter(self, queryset, request):
        """Add a filter to enforce a proprietary access period.

        Args:
            filters (dict): A filter dictionary to add the
        """
        if request.user.is_superuser:
            # superusers get no filtering
            logger.info("Allowing all data for superuser.")
            return queryset
        else:
            public_date_filter = Q(
                public_date__lte=get_observing_night(
                    datetime.datetime.now(tz=datetime.timezone.utc)
                )
            )
            if not request.user.is_authenticated:
                # Unknown users can only see public data
                logger.info("Only allowing public data for public user.")
                return queryset.filter(public_date_filter)
            else:
                # Authorized users can also see their proprietary data.
                authorized_user_filter = Q(user_access__obid__exact=request.user.obid)
                logger.info(
                    f"Allowing public data and proprietary data for user {request.user.username} (obid: {request.user.obid})"
                )
                return queryset.filter(public_date_filter | authorized_user_filter)

    def _build_range_filter(self, filters, orm_field_name, value1, value2):
        """Build a range filter for a field.

        Args:
            filters (dict):       A filter dictionary to add the filter to.
            orm_filed_name (str): The orm field to name to filter on, which may not be the same name used
                                  in the query string.
            value1 (object):      The first value in the range to filter by. The range will be re-arranged
                                  if value1 is not less than value2.
            value2 (object):      The second value in the range to filter by. The range will be re-arranged
                                  if value1 is not less than value2.
        """
        if value1 < value2:
            start_value = value1
            end_value = value2
        else:
            start_value = value2
            end_value = value1

        logger.debug(f"Using range {start_value}, {end_value}")
        filters[orm_field_name + "__range"] = (start_value, end_value)

    def _build_string_filter(self, filters, orm_field_name, value, operator):
        """Build a string filter for a field.

        Args:
            filters (dict):       A filter dictionary to add the filter to.
            orm_filed_name (str): The orm field to name to filter on, which may not be the same name used
                                  in the query string.
            value (str):          The value to filter by.
            operator (str):       One of ["eq","sw","cn", "eqi", "swi","cni"]
        """
        logger.debug(f"String filter value {value}")

        operator_map = {"eq": "exact", "sw": "startswith", "cn": "contains"}

        django_field_lookup = operator_map[operator[0:2]]
        sensitivity = "i" if operator[-1] == "i" else ""
        filters[f"{orm_field_name}__{sensitivity}{django_field_lookup}"] = value

    def _build_in_filter(self, filters, orm_field_name, values):
        """Build a filter for a field that will exactly match one of a fixed set of values.

        Args:
            filters (dict):       A filter dictionary to add the filter to.
            orm_filed_name (str): The orm field to name to filter on, which may not be the same name used
                                in the query string.
            values (list or Any): The value or values to filter by.
        """
        logger.debug(f"in filter value {values}")
        if not isinstance(values, list):
            values = [values]
        filters[f"{orm_field_name}__in"] = values

    def _build_contained_in_filter(self, filters, orm_field_name, coord, radius):
        """Build a filter for the PostgreSQL "<@" geometric operation that searches for
           coordinates within a circle.

        Args:
            filters (dict):       A filter dictionary to add the filter to.
            orm_filed_name (str): The orm field to name to filter on, which may not be the same name used
                                  in the query string.
            coord (SkyCoord):     The center of a circle on the sky.
            radius (Angle):       The angular radius of a circle.

        """
        logger.debug(f"in contained in filter {coord} {radius}")
        # To be a proper Django operation we'd have to make a custom
        # lookup, but since we're faking it with SQLAlchemy we don't have to
        filters[f"{orm_field_name}__contained_in"] = SCircle(coord, radius)

    def _build_exact_filter(self, filters, orm_field_name, value):
        """Build a filter for a field that will exactly match a value

        Args:
            filters (dict):       A filter dictionary to add the filter to.
            orm_filed_name (str): The orm field to name to filter on, which may not be the same name used
                                  in the query string.
            value (str):          The value to filter by.
        """
        logger.debug(f"exact filter value {value}")
        filters[orm_field_name + "__exact"] = value


class QueryAPIView:
    """Baseclass for views using the archive's QueryAPI to find/authorize access to files/file metadata."""

    def __init__(self, db_engine, table):
        self._db_engine = db_engine
        self._table = table

    def get_queryset(self):
        return SQLAlchemyQuerySet(self._db_engine, self._table)

    def get_object(self):
        log_request_debug(self.request)

        # Validate request using query serializer
        if self.lookup_url_kwarg not in self.kwargs:
            raise APIException(
                f"No {self.lookup_url_kwarg} specified.",
                code=status.HTTP_400_BAD_REQUEST,
            )
        value = self.kwargs[self.lookup_url_kwarg]
        data = {self.lookup_field: f"eq,{value}"}
        serializer = QuerySerializer(data=data, view=self)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            logger.error(f"Failed to validate {self.lookup_field}.", exc_info=True)
            raise

        # Store the validated results in the request to be passed to paginators and filters
        self.request.validated_query = serializer.validated_data

        logger.info(
            f"Getting object for {self.lookup_field} = {serializer.validated_data[self.lookup_field]}"
        )

        # Let the superclass filter the query set and then use that
        # to get the object.

        try:
            queryset = self.filter_queryset(self.get_queryset())

            # Return all of the acceptable result attributes
            queryset = queryset.values(*self.allowed_result_attributes)

            results = queryset[0:]
        except Exception as e:
            logger.error(
                f"Failed to get object from database for {self.lookup_field} = {serializer.validated_data[self.lookup_field]}: {e}",
                exc_info=True,
            )
            raise APIException(
                detail="Failed to query archive database.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if len(results) == 0:
            logger.error(
                f"{self.lookup_field} = {serializer.validated_data[self.lookup_field]} not found."
            )
            raise NotFound(detail="File not found")
        elif len(results) > 1:
            logger.error(
                f"Duplicate matches found for {self.lookup_field} = {serializer.validated_data[self.lookup_field]}, found {len(results)}"
            )
            raise APIException(
                detail="Failed to query archive database.",
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return results[0]
