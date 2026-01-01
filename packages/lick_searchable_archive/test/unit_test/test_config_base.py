import enum
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest
from lick_archive.config.config_base import (
    ConfigDict,
    ConfigFile,
    ConfigNamespace,
    ParsedURL,
)


@dataclass(kw_only=True)
class ConfigClassOne(ConfigNamespace):
    config_section_name = "test_section"

    test_int: int
    test_float: float = 1.5
    test_Str: str  # Also test case sensitivity
    test_bool_true_1: bool
    test_bool_true_2: bool
    test_bool_true_3: bool
    test_bool_false_1: bool
    test_bool_false_2: bool
    test_bool_false_3: bool
    test_url1: typing.Optional[ParsedURL]
    test_url2: ParsedURL

    def validate(self):
        if self.test_int < 1:
            raise ValueError("Value must be positive integer")
        return self


class EnumTest(enum.Enum):
    value1 = "value1"
    value2 = "value2"


@dataclass
class ConfigClassTwo(ConfigNamespace):
    config_section_name = "test_section_2"

    test_enum: EnumTest
    test_list: list[int]
    test_set: set
    test_tuple: tuple[str, bool]
    test_union_1: typing.Union[bool, int]
    test_union_2: typing.Union[bool, int]
    test_or_1: bool | int
    test_or_2: bool | int


@dataclass
class NestedConfigClass(ConfigNamespace):
    test_child_1: str
    test_child_2: int


@dataclass
class NestedTestConfig(ConfigNamespace):
    test_parent: str
    test_parent_int: int
    test_child: NestedConfigClass


class ConfigDictionaryTest(ConfigDict):
    config_section_name = "test_lookup"
    value_type = list[str]


class ConfigDictionaryDefaultTest(ConfigDict):
    config_section_name = "test_default_lookup"
    value_type = list[int]
    default_key_name = "default"


class ConfigClassFile(ConfigFile):
    config_classes = [
        ConfigClassOne,
        ConfigClassTwo,
        NestedTestConfig,
        ConfigDictionaryTest,
        ConfigDictionaryDefaultTest,
    ]


test_data_dir = Path(__file__).parent / "test_data"


def test_valid_configs():
    valid_config_file = ConfigClassFile.from_file(test_data_dir / "test_config.ini")

    valid_one = valid_config_file.test_section
    assert valid_one.test_int == 3
    assert valid_one.test_float == -0.5
    assert valid_one.test_Str == "hello"
    assert valid_one.test_bool_true_1 is True
    assert valid_one.test_bool_true_2 is True
    assert valid_one.test_bool_true_3 is True
    assert valid_one.test_bool_false_1 is False
    assert valid_one.test_bool_false_2 is False
    assert valid_one.test_bool_false_3 is False
    assert str(valid_one.test_url1) == "http://example.org/"
    assert (
        valid_one.test_url2.url
        == "https://example.org:8000/archive/index?query1=2&query2=test#fragment"
    )

    valid_two = valid_config_file.test_section_2
    assert valid_two.test_enum == EnumTest.value1
    assert valid_two.test_list == [1, 2, 3]
    assert valid_two.test_set == {"2", "blue", "True"}
    assert valid_two.test_tuple == ("one", True)
    assert valid_two.test_union_1 is True
    assert valid_two.test_union_2 == 3
    assert valid_two.test_or_1 is True
    assert valid_two.test_or_2 == 3

    valid_nested = valid_config_file.nestedtest
    assert valid_nested.test_parent == "parent"
    assert valid_nested.test_child.test_child_1 == "child"
    assert valid_nested.test_child.test_child_2 == 3
    assert valid_nested.test_parent_int == 5

    valid_lookup = valid_config_file.test_lookup
    assert valid_lookup["test_key1"] == ["one", "two", "three"]
    assert valid_lookup["TEST_KEY2"] == ["1", "2", "3"]
    assert "test_key3" not in valid_lookup
    with pytest.raises(KeyError):
        valid_lookup["test_key3"]

    # Other dict method tests
    keys = list(valid_lookup.keys())
    assert "test_key1" in keys
    assert "TEST_KEY2" in keys
    assert len(valid_lookup) == 2

    valid_lookup = valid_config_file.test_default_lookup
    assert valid_lookup["test_one"] == [1, 2, 3]
    # Default value for empty keys in the config value
    assert valid_lookup["test_two"] == [0, 0, 0]
    assert valid_lookup["test_three"] == [0, 0, 0]
    # Default of a missing key in the config values
    assert valid_lookup["does not exist"] == [0, 0, 0]
    assert len(valid_lookup) == 3


def test_missing():
    # Test a config that uses a default value

    config_parser = ConfigFile.get_config_parser()
    config_parser.read(test_data_dir / "test_config.ini")
    valid_config = ConfigClassOne.from_config_section(
        config_parser, config_parser["test missing default"]
    )
    assert valid_config.test_float == 1.5

    # Test an invalid config missing a required value
    with pytest.raises(ValueError, match="Missing attribute 'test_int'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test missing required"]
        )

    # Test an config missing an optional value
    valid_config = ConfigClassOne.from_config_section(
        config_parser, config_parser["test missing optional"]
    )
    assert valid_config.test_url1 is None

    # Test an invalid config missing a required value due to case mismatch
    with pytest.raises(ValueError, match="Missing attribute 'test_Str'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test missing case mismatch"]
        )


def test_invalid():
    config_parser = ConfigFile.get_config_parser()
    config_parser.read(test_data_dir / "test_config.ini")

    with pytest.raises(ValueError, match="invalid literal for int"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test invalid int"]
        )

    with pytest.raises(ValueError, match="Invalid boolean value 'maybe'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test invalid bool"]
        )

    with pytest.raises(ValueError, match="is not a valid EnumTest"):
        invalid_config = ConfigClassTwo.from_config_section(
            config_parser, config_parser["test invalid enum"]
        )

    with pytest.raises(ValueError, match="invalid literal for int"):
        invalid_config = ConfigClassTwo.from_config_section(
            config_parser, config_parser["test invalid typed list"]
        )

    with pytest.raises(
        ValueError, match="Length of tuple 4 does not match expected length 2"
    ):
        invalid_config = ConfigClassTwo.from_config_section(
            config_parser, config_parser["test invalid typed tuple"]
        )

    with pytest.raises(
        ValueError,
        match=r"Invalid boolean value 'blue'\s+invalid literal for int\(\) with base 10: 'blue'",
    ):
        invalid_config = ConfigClassTwo.from_config_section(
            config_parser, config_parser["test invalid union"]
        )

    with pytest.raises(
        ValueError,
        match=r"Invalid boolean value 'blue'\s+invalid literal for int\(\) with base 10: 'blue'",
    ):
        invalid_config = ConfigClassTwo.from_config_section(
            config_parser, config_parser["test invalid or"]
        )


def test_empty():
    config_parser = ConfigFile.get_config_parser()
    config_parser.read(test_data_dir / "test_config.ini")

    with pytest.raises(ValueError, match="Missing attribute 'test_Str'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test empty string"]
        )

    with pytest.raises(ValueError, match="attribute 'test_bool_true_1'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test empty bool"]
        )

    # Should use default value
    valid_config = ConfigClassOne.from_config_section(
        config_parser, config_parser["test empty float"]
    )
    assert valid_config.test_float == 1.5

    with pytest.raises(ValueError, match="Missing attribute 'test_url2'"):
        invalid_config = ConfigClassOne.from_config_section(
            config_parser, config_parser["test empty url"]
        )

    valid_config = ConfigClassOne.from_config_section(
        config_parser, config_parser["test empty optional url"]
    )
    assert valid_config.test_url1 is None


def test_invalid_lookups():
    config_parser = ConfigFile.get_config_parser()
    config_parser.read(test_data_dir / "test_config.ini")

    # Test a default dictionary with no default value succeeds on the value given, and returns None on an unknown value
    valid_config = ConfigDictionaryDefaultTest.from_config_section(
        config_parser, config_parser["test empty default lookup"]
    )
    assert valid_config["test_one"] == [1, 2, 3]
    assert valid_config["test_two"] == None

    # Test a dictionary with a value that doesn't match the expected type
    with pytest.raises(ValueError, match="invalid literal for int"):
        invalid_config = ConfigDictionaryDefaultTest.from_config_section(
            config_parser, config_parser["test invalid lookup"]
        )

    # Test a dictionary with a default value that doesn't match the expected type
    with pytest.raises(ValueError, match="invalid literal for int"):
        invalid_config = ConfigDictionaryDefaultTest.from_config_section(
            config_parser, config_parser["test invalid default"]
        )
