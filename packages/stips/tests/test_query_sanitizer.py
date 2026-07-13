"""Tests for the Butler WHERE-literal sanitizer (F-018).

butler_str_literal validates user/header-derived values before they are
interpolated into Butler WHERE expressions, rejecting anything that could break
out of the string literal or inject additional query terms.
"""

import pytest

from stips.core.query import butler_str_literal


# Every real target/band value that flows through a WHERE clause in the repo.
@pytest.mark.parametrize(
    "value",
    [
        "2023ixf",
        "2020wnt",
        "AC_Andromedae",
        "CY_Aquarii",
        "HAT-P-32",
        "HD_189733",
        "PG1047+003",
        "PG1633+099",
        "V0678-Oph",
        "landolt_validation",
        "107_458",  # Landolt fits_object
        "PG1323-086",
        "SN 2023ixf",  # a space is allowed
        "r",  # single-letter band
        "b",
    ],
)
def test_accepts_real_target_and_band_names(value):
    assert butler_str_literal(value) == f"'{value}'"


@pytest.mark.parametrize(
    "value",
    [
        "x'; DROP TABLE",  # single quote -> injection
        "a' OR '1'='1",  # classic injection
        "2023ixf'",  # trailing quote breaks out of the literal
        'a"b',  # double quote
        "back`tick`",  # backtick
        "semi;colon",  # statement separator
        "paren()",  # parentheses
        "star*",  # glob/wildcard
        "eq=val",  # equals
        "",  # empty is not a valid literal
    ],
)
def test_rejects_injection_and_out_of_charset(value):
    with pytest.raises(ValueError):
        butler_str_literal(value)


def test_error_message_names_the_value():
    with pytest.raises(ValueError, match="Unsafe value"):
        butler_str_literal("bad'value")
