from __future__ import annotations  # To allow a class to return itself

import abc
import configparser
import inspect
import re
import types
import typing
from collections import UserDict
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse


class ParsedURL:
    """A class representing a parsed URL that can still be passed as an URL to requests.
    Only http and https URLs are allowed.

    Args:
       url: The URL to parse

    Attributes:
        url    (str): The whole URL
    Raises:
        ValueError if the value is not a valid URL

    """

    allowed_schemes = ["http", "https"]
    """The allowed URL schemes, intended to be overridden by a child class."""

    def __init__(self, url: str):
        result = urlparse(url)
        if result.scheme not in self.allowed_schemes:
            raise ValueError(
                f"{url} does not have an allowed scheme. The allowed schemes are: {','.join(self.allowed_schemes)}"
            )

        if result.netloc == "":
            raise ValueError(f"{url} does not have a valid network location.")
        self.url = url
        self.parsed_url = result

    def __str__(self) -> str:
        """Return URL as a string"""
        return self.url

    def __add__(self, other: str) -> ParsedURL:
        """Return a new URL with a string appended to it."""
        return ParsedURL(self.url + other)


class PostgreSQLURL(ParsedURL):
    """A URL for connecting to a PostgreSQL database, as specified in the
    `PostgreSQL documentation <https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING>`_
    """

    allowed_schemes = ["postgresql", "postgres"]


class ConfigBase(abc.ABC):

    def validate(self):
        """Method to perform post parsing validation. This is intended to be inherited by
        subclasses and is called after creating the config class from an ini file.

        Child classes should raise an exception if the configuration is not valid. Otherwise
        They should return the validated object.  The default implementation simply returns self.
        """
        return self

    @classmethod
    def get_section_name(cls):
        """Return the section name used in the config file for this class. This can be set by child classes in the
        ``config_section_name`` class attribute, otherwise it defaults to the classname, lowercase, with "Config" removed
        from the end
        """
        if hasattr(cls, "config_section_name"):
            return cls.config_section_name
        else:
            return cls.__name__.removesuffix("Config").lower()

    @classmethod
    @abc.abstractmethod
    def from_config_section(
        cls, config_file: typing.Mapping, config_section: typing.Mapping
    ):
        pass

    @classmethod
    def from_config_file(cls, config_file: typing.Mapping):
        return cls.from_config_section(config_file, config_file[cls.get_section_name()])

    @classmethod
    def _read_typed_value_from_config(
        cls,
        type_object: typing.Callable,
        config_file: typing.Mapping,
        config_section: typing.Mapping,
        attribute_name: str,
        default: typing.Any = inspect.Parameter.empty,
    ) -> typing.Any:
        """Read an attribute of a given type from a configparser section."""

        possible_types = cls._get_possible_types(type_object)
        if len(possible_types) == 0:
            raise ValueError(
                f"Config class '{cls.__name__}' __init__ method uses unsupported type '{type_object}' for parameter: '{attribute_name}'"
            )

        # See if the attribute exists
        is_missing = (
            attribute_name not in config_section
            or config_section[attribute_name] is None
            or len(config_section[attribute_name]) == 0
        )

        validation_errors = []

        # Try each possible type to see if it can parse the attribute
        for possible_type in possible_types:

            # Get type arguments, for container types like list[str],
            type_origin = typing.get_origin(possible_type)

            if type_origin is not None:
                type_args = typing.get_args(possible_type)
                possible_type = type_origin
            else:
                type_args = []

            if not isinstance(possible_type, type):
                # This could happen if the type is something like "typing.Annotated"
                validation_errors.append(f"Unsupported type '{possible_type}'")
                continue

            # Look for a nested subclass. Note this may not have an option in the ini file
            if issubclass(possible_type, ConfigBase):
                # Let a nested subclass parse itself
                return possible_type.from_config_file(config_file)

            if is_missing:
                if possible_type == types.NoneType:
                    # An optional attribute
                    return None
                else:
                    # See if another type can handle a missing attribute
                    continue

            try:
                if (
                    not is_missing
                    and possible_type is list
                    or possible_type is tuple
                    or possible_type is set
                ):
                    # Sequence types
                    string_values = [
                        s.strip() for s in config_section[attribute_name].split(",")
                    ]

                    if len(type_args) == 0:
                        # Default to string values if there's no typing
                        typed_values = string_values
                    elif len(type_args) == 1:
                        # One type for every element
                        typed_values = [
                            cls._parse_value(type_object=type_args[0], value=v)
                            for v in string_values
                        ]
                    elif len(type_args) == len(string_values):
                        # Each element must match it's corresponding type
                        typed_values = [
                            cls._parse_value(type_object=t, value=v)
                            for v, t in zip(string_values, type_args)
                        ]
                    else:
                        validation_errors.append(
                            f"Length of {possible_type.__name__} {len(string_values)} does not match expected length {len(type_args)}"
                        )
                        continue
                    # Create the sequence objects with its individual elements
                    return possible_type(typed_values)
                else:
                    # A non-sequence type, directly parse it
                    return cls._parse_value(
                        type_object=possible_type, value=config_section[attribute_name]
                    )
            except Exception as e:
                validation_errors.append(str(e))
                continue

        if is_missing:
            # The attribute was missing and empty and there was no type
            # that could deal with that. Use the default value if one was provided
            # or raise an errror
            if default != inspect.Parameter.empty:
                return default
            else:
                raise ValueError(
                    f"Missing attribute '{attribute_name}' in section '{config_section.name}"
                )

        # If we've reached this point we didn't successfully parse the attribute value
        msg = f"Failed to parse Config section '[{config_section.name}]' attribute '{attribute_name}'"
        if len(validation_errors) > 0:
            msg += "\n    " + "\n    ".join(validation_errors)
        raise ValueError(msg)

    @classmethod
    def _get_possible_types(cls, type_object):
        """Given a type object, see if it's a union/optional type that can support
        multiple types, and return those individual types
        """
        type_origin = typing.get_origin(type_object)
        if type_origin is None:
            # Not a special annotated type
            possible_types = typing.get_args(type_object)
            if len(possible_types) == 0:
                possible_types = [type_object]
        elif (
            (type_origin is typing.Union)
            or (type_origin is typing.Optional)
            or (type_origin is types.UnionType)
        ):
            # Types that accept multiple types
            possible_types = typing.get_args(type_object)
        else:
            # Some other special type, hopefully we can deal with it in _read_typed_value_from_config of _parse_value
            possible_types = [type_object]

        return possible_types

    @classmethod
    def _parse_value(cls, type_object: typing.Callable, value: str) -> typing.Any:
        """Parse a string value as a type"""
        if type_object is types.NoneType:
            # Return optional values as None if they're empty
            if value is None or len(value) == 0:
                return None

        elif type_object is str:
            # Make sure strings aren't empty
            if len(value) == 0:
                raise ValueError("Empty value")
            else:
                return value
        elif type_object is bool:
            # Parse the boolean allowing true/false 1/0 or yes/no.
            if value.lower() in ["true", "1", "yes"]:
                return True
            elif value.lower() in ["false", "0", "no"]:
                return False
            else:
                raise ValueError(f"Invalid boolean value '{value}'")
        else:
            # For other types, let the type_object constructor do the parsing
            return type_object(value)


class ConfigNamespace(ConfigBase):

    @classmethod
    def from_config_section(
        cls, config_file: typing.Mapping, config_section: typing.Mapping
    ):
        # Find the init arguments the subclass takes
        init_signature = inspect.signature(cls.__init__)

        # Build the keyword arguments to build the subclass
        child_init_kwargs = {}
        for attr in init_signature.parameters:

            if attr == "self":
                # Don't count "self"
                continue

            # Try to get the attribute from the config section
            default_value = init_signature.parameters[attr].default
            attr_type = init_signature.parameters[attr].annotation
            child_init_kwargs[attr] = cls._read_typed_value_from_config(
                attr_type, config_file, config_section, attr, default=default_value
            )

        # Build and validate the object with the parsed data
        return cls(**child_init_kwargs).validate()


class ConfigDict(ConfigBase, UserDict):

    value_type: type = str
    """The value types for values in this section. Defaults to str"""

    default_key_name: str = None
    """The name of a 'default' key that defines the default value for any keys not found in the config section.
    Defaults to None, meaning there is no default value and a KeyError will be raised for unknown keys."""

    @classmethod
    def from_config_section(
        cls, config_file: typing.Mapping, config_section: typing.Mapping
    ):

        # Our default_value. It can be overriden by the default_key_name in the config_section
        # But only if the default_key_name is defined
        default_value = None

        d = dict()

        for key in config_section.keys():
            if cls.default_key_name is not None:
                parsed_value = cls._read_typed_value_from_config(
                    cls.value_type,
                    config_file,
                    config_section,
                    key,
                    default=default_value,
                )

                if key == cls.default_key_name:
                    default_value = parsed_value
                    continue
            else:
                parsed_value = cls._read_typed_value_from_config(
                    cls.value_type, config_file, config_section, key
                )

            d[key] = parsed_value

        # Build the object with the parsed data
        return cls(
            d,
            allow_default=cls.default_key_name is not None,
            default_value=default_value,
        ).validate()

    def __init__(self, mapping: Mapping, allow_default=False, default_value=None):
        super().__init__(mapping)
        self.allow_default = allow_default
        self.default_value = default_value

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        elif self.allow_default is True:
            return self.default_value
        else:
            raise KeyError(f"{key} not found in {self.__class__.__name__}.")


class ConfigFile:
    config_classes = []
    config = None

    def __init__(self, sections):
        for section, object in sections.items():
            self.__setattr__(section, object)

    @classmethod
    def get_config_parser(cls) -> configparser.ConfigParser:
        # Construct the config parser to allow keys with no values. For example:
        # [section]
        # Key1
        # Key2 = blah
        config_parser = configparser.ConfigParser(allow_no_value=True)
        # Have the config parser preserve case of keys. So that "Key1" and "key1" will
        # be considered different keys.
        config_parser.optionxform = lambda x: x

        # Allow whitespace around section names. So that [section] and [  section ] are the same.
        config_parser.SECTCRE = re.compile(r"\[\s*(?P<header>[^]]*\S)\s*]")

        return config_parser

    @classmethod
    def from_file(cls, file: str | Path) -> ConfigFile:

        if cls.config is None:

            # Now parse the file
            config_parser = cls.get_config_parser()

            if isinstance(file, str):
                file = Path(file)
            if not file.exists():
                raise ValueError(f"Config file {file} does not exist.")

            config_parser.read(file)
            sections = {}
            for config_cls in cls.config_classes:
                section_name = config_cls.get_section_name()

                if section_name not in config_parser.sections():
                    raise ValueError(
                        f"Config file {file} missing '{section_name}' section."
                    )

                # Allow for mixed case section names with spaces in the config file, but convert those to
                # lowercase with underscores to use as the attribute name of the ConfigFile object.
                attribute_name = section_name.lower().replace(" ", "_")
                config_section = config_parser[section_name]

                sections[attribute_name] = config_cls.from_config_section(
                    config_parser, config_section
                )

            cls.config = cls(sections)
        return cls.config
