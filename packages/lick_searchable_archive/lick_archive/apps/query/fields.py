"""Custom serializer fields used when validating queries"""

import logging

logger = logging.getLogger(__name__)

import datetime
import re
import typing

from astropy import units
from astropy.coordinates import Angle, SkyCoord
from django.utils.dateparse import parse_date, parse_datetime
from lick_archive.config.archive_config import ArchiveConfigFile
from lick_archive.utils.django_utils import validate_chars
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class ISODateOrDateTimeField(serializers.Field):
    """A custom field that can be either an ISO date or datetime. This will
    translate the value to either a python datetime.datetime or datetime.date
    object depending on whether time information is included in the input."""

    def to_internal_value(self, data: typing.Any):
        """Convert a value to either a datetime.date or datetime.datetime object

        Args:
            data (Any): The data to convert.
        Return:
            (datetime or date): The converted value. Any datetime objects returned will have
                                the timezone set.

        Raises:
            ValidationError: Raised if the passed in data is not a valid date or datetime.
        """
        if isinstance(data, datetime.date):
            return data
        elif isinstance(data, datetime.datetime):
            return data
        elif isinstance(data, str):
            try:
                result = parse_date(data)
                if result is None:
                    # Try as a datetime
                    result = parse_datetime(data)

                    if result is None:
                        raise ValidationError(
                            "Date has the wrong format. Expected an ISO-8601 date or datetime."
                        )
                    if result.tzinfo is None:
                        # Force UTC
                        result = datetime.datetime.combine(
                            result.date(), result.time(), datetime.timezone.utc
                        )
            except ValueError:
                # Problem parsing date
                logger.error("Failed parsing date", exc_info=True)
                raise ValidationError(
                    "Date has the wrong format. Expected an ISO-8601 date or datetime."
                )

            return result
        else:
            raise ValidationError(
                "Incorrect data type for date. Expected datetime, date, or string."
            )

    def to_representation(self, value):
        """Convert a datetime/date object to it's string representation
        Args:
            value (None, date, datetime): The value to convert.

        Return: (str or None): The converted value, or None if the input was None.
        """
        if value is None:
            return None
        elif isinstance(value, datetime.date) or isinstance(value, datetime.datetime):
            return value.isoformat()
        else:
            # I don't know why this would happen, but I don't trust the frame work
            raise ValidationError(
                "Not a valid data type. Expected datetime, date, or None."
            )


class ListWithSeperator(serializers.ListField):
    """
    A custom list field that supports items seperated by a seperator character. This is used to
    support URL query strings like "results=filename,object,obs_date"

    Because it derives from the DRF ListField, it also supports multiple uses of a field in the query
    parameters, e.g.: "results=filename&results=object,obs_date"

    Args:
        sep_char (str):  The seperator character.
    """

    def __init__(self, sep_char, **kwargs):
        super().__init__(**kwargs)

        if len(sep_char) != 1:
            raise ValueError("sep_char must be a single character")
        self.sep_char = sep_char

    def to_internal_value(self, data):
        """Override to_internal_value to convert a string to a list split by our seperatar character."""

        if isinstance(data, list):
            split_data = []
            for item in data:
                split_data += item.split(self.sep_char)
        else:
            split_data = data

        return super().to_internal_value(split_data)


class QueryField(serializers.CharField):
    """Custom field type for a field being queried on, consisting of an operator and one or more values.

    The fields are specified in the URL query parameters as follows:
    "fieldname=operator,value1,value2...,valueN"
    """

    default_error_messages = {
        "invalid": "Invalid query parameter type {invalid_type}.",
        "missing_operator": "Missing query operator. Allowed operators are: {allowed_operators}.",
        "unknown_operator": "Unsupported operator. Allowed operators are: {allowed_operators}.",
        "missing_value": "Missing value to query with.",
        "too_many_values": "Too many values specified.",
    }

    def __init__(
        self,
        operators: list[str],
        value,
        max_num_values=1,
        split_values=False,
        allow_empty=False,
        max_length=None,
        max_value_length=None,
        **kwargs
    ):
        """Initialize a query field.
        Args:
            operators:        A list of the operators supported for this field.
            value:            The serializer field for parsing/validating each value passed to the query
            split_values:     Whether or not to split the values into a list.
            allow_empty:      If true an operator with no values is allowed.
            max_num_values:   The maximum number of values allowed.Only applicable if split_values is True.
            max_length:       The maximum length of the field, as in the CharField keyword arguments.
            max_value_length: The maximum length of an individual value. If "max_length" is not specified this
                              is used to calculate the maximum length.

        Other keyword arguments of serializers.CharField are also supported.
        """

        self._operators = operators
        self._value_field = value
        self._split_values = split_values
        self._max_num_values = 1 if not self._split_values else max_num_values
        self._allow_empty = allow_empty

        if max_length is None and max_value_length is not None:
            # Calculate max_length based on max_value_length

            # Operators + comma
            max_op_length = max(map(len, self._operators)) + 1

            # Include max length of value(s) + commas
            max_values_length = max_value_length * max_num_values + max_num_values - 1

            max_length = max_op_length + max_values_length

        super().__init__(max_length=max_length, **kwargs)

    def to_internal_value(self, data):
        """Parse and validate data into a list of [operator, value1, value2...,valueN]"""
        if not isinstance(data, str):
            self.fail("invalid", invalid_type=type(data).__name__)

        # Parameters of the query are separated by a comma. If we're not splitting the values
        # only one split is needed to separate the operator from the value.
        split_data = data.split(",", -1 if self._split_values else 1)

        # Parse operator
        if len(split_data) == 0:
            self.fail("missing_operator", allowed_operators=self._operators)
        operator = split_data[0].strip().lower()
        if operator not in self._operators:
            self.fail("unknown_operator", allowed_operators=self._operators)

        # Parse values
        if len(split_data) < 2:
            if not self._allow_empty:
                self.fail("missing_value")
            values = [""]
        else:
            unvalidated_values = split_data[1:]
            if len(unvalidated_values) > self._max_num_values:
                self.fail("too_many_values")

            # Run validation using the value's serializer field
            values = [
                self._value_field.run_validation(item.strip())
                for item in unvalidated_values
            ]
        return [operator] + values


class CoordField(serializers.CharField):
    """A custom serializer field for parsing and validating a coordinate and radius for a coordinate query."""

    # Regular expressions for parsing Angles
    _sexagesimal_spaces = re.compile(
        r"^([+-]?\d+) +(\d{1,2}) +((?:\d{1,2}(?:\.\d+)?)|(?:\.\d+))$"
    )
    _sexagesimal_colon = re.compile(
        r"^([+-]?\d+):(\d{1,2}):((?:\d{1,2}(?:\.\d+)?)|(?:\.\d+))$"
    )
    _sexagesimal_letters = re.compile(
        r"^([+-]?\d+) *([hdHD]) *(\d{1,2}) *[mM] *(?:((?:\d{1,2}(?:\.\d+)?)|(?:\.\d+)) *[sS])?$"
    )
    _decimal_unit = re.compile(
        r"^([+-]?(?:(?:\d+(?:\.\d+)?)|(?:\.\d+))) *([HDMShdms]?)$"
    )

    _angle_allowed_chars = "+- :0123456789.DHMSdhms"

    default_error_messages = {
        "invalid": "Invalid query parameter type {invalid_type}.",
        "too_long": "Query parameter too long.",
        "invalid_format": "Coordinate value should consist of ra, dec and an optional radius.",
        "invalid_angle": "Invalid angle specified for {field}.",
        "invalid_angle_msg": "Invalid angle specified for {field}: {msg}",
        "invalid_dec": "DEC must be between -90 and 90 degrees",
        "invalid_coord": "Invalid coordinate: {msg}",
        "negative_radius": "Radius must be >0",
    }

    def __init__(self, default_radius: Angle, **kwargs):
        """Initialize a coord field

        Args:
            default_radius: The default radius to use if one is not specified.
        """

        self.default_radius = Angle(default_radius)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        """Parse a coord query parameter to (coord, radius), where the values
        are stored as Astropy SkyCoord and Angle values
        """
        if not isinstance(data, str):
            self.fail("invalid", invalid_type=type(data).__name__)

        # Make sure the length is sane
        if len(data) > 100:
            self.fail("too_long")

        split_data = data.split(",")

        # There should be at least two values (an ra and dec) with an optional radius
        if len(split_data) < 2 or len(split_data) > 3:
            self.fail("invalid_format")

        # Parse RA/DEC
        ra = self.parse_coord_angle(split_data[0].strip(), "RA", units.hourangle)
        dec = self.parse_coord_angle(split_data[1].strip(), "DEC", units.deg)

        # Make sure dec is in range
        if dec < Angle(-90.0, unit=units.deg) or dec > Angle(90.0, unit=units.deg):
            self.fail("invalid_dec")

        # Parse optional radius
        if len(split_data) == 3 and len(split_data[2].strip()) > 0:

            validate_chars(
                split_data[2].strip(), self._angle_allowed_chars, error_label="Radius"
            )

            radius = self.parse_decimal_angle(
                split_data[2].strip(), "Radius", units.arcsec
            )
            if radius is None:
                self.fail("invalid_angle", field="Radius")
        else:
            radius = self.default_radius

        if radius <= Angle(0, units.deg):
            self.fail("negative_radius")

        try:
            coord = SkyCoord(ra, dec)
        except Exception as e:
            self.fail("invalid_coord", msg=str(e))

        return (coord, radius)

    def parse_coord_angle(
        self, input_angle: str, field: str, default_unit: units.Unit
    ) -> Angle:
        """Parse one of the angles in a coordinate. The following formats are supported:

        123:45:67.89
        123 45 67.89
        123h 45d 67.89s
        123.45678d
        123.45678

        Args:
            input_angle:  The input string to be parsed and validated.
            field:        The name of the field being validated. Used for error messages.
            default_unit: The default unit to use if one isn't specified by the input.

        Return: The parsed angle.
        """
        # Make sure it's not an empty string
        if len(input_angle) == 0:
            self.fail("missing_angle", field=field)

        # Validate there's no invalid characters
        validate_chars(input_angle, self._angle_allowed_chars, error_label=field)

        # First try a sexagesimal angle, then a decimal angle
        try:
            angle = self.parse_sexagesimal_angle(input_angle, default_unit)
            if angle is None:
                angle = self.parse_decimal_angle(input_angle, field, units.deg)

            if angle is None:
                self.fail("invalid_angle", field=field)
        except ValidationError:
            raise
        except Exception as e:
            # Convert other exceptions, such as ones from Astropy to ValidationErrors
            self.fail("invalid_angle_msg", field=field, msg=str(e))

        return angle

    def parse_sexagesimal_angle(
        self, input_angle: str, default_unit: units.Unit
    ) -> Angle | None:
        """Parse a sexagesimal angle.
        Args:
            input_angle:  The input string to be parsed and validated.
            default_unit: The default unit to use if one isn't specified by the input.

        Return: The parsed angle or None if the input value is not a sexagesimal angle.
        """
        angle_units = default_unit

        # Check for a match which each sexagesimal regular expression
        match = self._sexagesimal_spaces.fullmatch(input_angle)
        if match is None:
            match = self._sexagesimal_colon.fullmatch(input_angle)
            if match is None:
                match = self._sexagesimal_letters.fullmatch(input_angle)
                if match is None:
                    # Not a sexagesimal angle
                    return None
                else:
                    # sexagesimal with letters specifies a unit, so we don't have to provide one
                    angle_units = None

                    # However it is case sensitive, so we convert it to lowercase for astropy
                    input_angle = input_angle.lower()

        return Angle(input_angle, unit=angle_units)

    def parse_decimal_angle(
        self, input_angle: str, field: str, default_unit: units.Unit
    ) -> Angle | None:
        """Parse a decimal angle with optional unit.
        Args:
            input_angle:  The input string to be parsed and validated.
            default_unit: The default unit to use if one isn't specified by the input.

        Return: The parsed angle or None if the input value is not a decimal angle.
        """

        match = self._decimal_unit.fullmatch(input_angle)

        if match is None:
            return None

        if match.group(2) is not None and match.group(2) != "":
            # The angle included units
            angle_units = None
        else:
            angle_units = default_unit

        # We support case insensitive units, but Astropy doesn't, so we convert to lower case
        try:
            angle = Angle(input_angle.lower(), unit=angle_units)
        except Exception as e:
            # Convert Astropy exception to ValidationError
            self.fail("invalid_angle_msg", field=field, msg=str(e))
        return angle
