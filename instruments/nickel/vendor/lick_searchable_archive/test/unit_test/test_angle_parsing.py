def test_angle_field_space_regex():
    from lick_archive.apps.query.fields import CoordField

    match = CoordField._sexagesimal_spaces.fullmatch("123  45 67")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == "67"

    match = CoordField._sexagesimal_spaces.fullmatch("123 4  6")
    assert match.group(1) == "123"
    assert match.group(2) == "4"
    assert match.group(3) == "6"

    match = CoordField._sexagesimal_spaces.fullmatch("123 4 6.890")
    assert match.group(1) == "123"
    assert match.group(2) == "4"
    assert match.group(3) == "6.890"

    match = CoordField._sexagesimal_spaces.fullmatch("123 45 67.890")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_spaces.fullmatch("+123 45 67.890")
    assert match is not None
    assert match.group(1) == "+123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_spaces.fullmatch("-123 45 67.890")
    assert match is not None
    assert match.group(1) == "-123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_spaces.fullmatch("123 45 .890")
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == ".890"

    # Below are the two examples from the simbad coordinate query page
    match = CoordField._sexagesimal_spaces.fullmatch("20 54 05.689")
    assert match.group(1) == "20"
    assert match.group(2) == "54"
    assert match.group(3) == "05.689"

    match = CoordField._sexagesimal_spaces.fullmatch("+37 01 17.38")
    assert match.group(1) == "+37"
    assert match.group(2) == "01"
    assert match.group(3) == "17.38"

    invalid_strings = [
        "45  67.890",
        "67.890",
        "123",
        "+-123 45 67.890",
        "123 -45 67.890",
        "123 45 +67.890",
        "123 45 67.",
        "123 456 67",
        "123 45 678",
        "+",
        "-",
        " ",
        "",
    ]

    for s in invalid_strings:
        assert CoordField._sexagesimal_spaces.fullmatch(s) is None


def test_angle_field_colon_regex():
    from lick_archive.apps.query.fields import CoordField

    match = CoordField._sexagesimal_colon.fullmatch("123:45:67")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == "67"

    match = CoordField._sexagesimal_colon.fullmatch("123:4:6")
    assert match.group(1) == "123"
    assert match.group(2) == "4"
    assert match.group(3) == "6"

    match = CoordField._sexagesimal_colon.fullmatch("123:4:6.890")
    assert match.group(1) == "123"
    assert match.group(2) == "4"
    assert match.group(3) == "6.890"

    match = CoordField._sexagesimal_colon.fullmatch("123:45:67.890")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_colon.fullmatch("+123:45:67.890")
    assert match is not None
    assert match.group(1) == "+123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_colon.fullmatch("-123:45:67.890")
    assert match is not None
    assert match.group(1) == "-123"
    assert match.group(2) == "45"
    assert match.group(3) == "67.890"

    match = CoordField._sexagesimal_colon.fullmatch("123:45:.890")
    assert match.group(1) == "123"
    assert match.group(2) == "45"
    assert match.group(3) == ".890"

    # Below are the two examples from the simbad coordinate query page
    match = CoordField._sexagesimal_colon.fullmatch("10:12:45.3")
    assert match.group(1) == "10"
    assert match.group(2) == "12"
    assert match.group(3) == "45.3"

    match = CoordField._sexagesimal_colon.fullmatch("-45:17:50")
    assert match.group(1) == "-45"
    assert match.group(2) == "17"
    assert match.group(3) == "50"

    invalid_strings = [
        "45:67.890",
        "67.890",
        "123",
        "123::",
        "123:",
        "+-123:45:67.890",
        "123:+45:67.890",
        "123:45:-67.890",
        "123:45:67.",
        "123:456:67",
        "123:45:678",
        "::",
        "+",
        "-",
        " ",
        "",
    ]

    for s in invalid_strings:
        assert CoordField._sexagesimal_colon.fullmatch(s) is None


def test_angle_field_letter_regex():
    from lick_archive.apps.query.fields import CoordField

    match = CoordField._sexagesimal_letters.fullmatch("123h45m67s")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "h"
    assert match.group(3) == "45"
    assert match.group(4) == "67"

    match = CoordField._sexagesimal_letters.fullmatch("123 d 45 m 67 s")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == "67"

    match = CoordField._sexagesimal_letters.fullmatch("123h4m6s")
    assert match.group(1) == "123"
    assert match.group(2) == "h"
    assert match.group(3) == "4"
    assert match.group(4) == "6"

    match = CoordField._sexagesimal_letters.fullmatch("123H4M 6.890S")
    assert match.group(1) == "123"
    assert match.group(2) == "H"
    assert match.group(3) == "4"
    assert match.group(4) == "6.890"

    match = CoordField._sexagesimal_letters.fullmatch("123 d 45 m 67.890 s")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == "67.890"

    match = CoordField._sexagesimal_letters.fullmatch("123d 45m 67.890s")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == "67.890"

    match = CoordField._sexagesimal_letters.fullmatch("+123d 45m 67.890s")
    assert match is not None
    assert match.group(1) == "+123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == "67.890"

    match = CoordField._sexagesimal_letters.fullmatch("-123d 45m 67.890s")
    assert match is not None
    assert match.group(1) == "-123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == "67.890"

    match = CoordField._sexagesimal_letters.fullmatch("123D 45m67.890s")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "D"
    assert match.group(3) == "45"
    assert match.group(4) == "67.890"

    match = CoordField._sexagesimal_letters.fullmatch("123d 45m .890s")
    assert match.group(1) == "123"
    assert match.group(2) == "d"
    assert match.group(3) == "45"
    assert match.group(4) == ".890"

    # Below are examples from the simbad coordinate query page
    match = CoordField._sexagesimal_letters.fullmatch("15h17m")
    assert match.group(1) == "15"
    assert match.group(2) == "h"
    assert match.group(3) == "17"
    assert match.group(4) is None

    match = CoordField._sexagesimal_letters.fullmatch("-11d10m")
    assert match.group(1) == "-11"
    assert match.group(2) == "d"
    assert match.group(3) == "10"
    assert match.group(4) is None

    match = CoordField._sexagesimal_letters.fullmatch("275d11m15.6954s")
    assert match.group(1) == "275"
    assert match.group(2) == "d"
    assert match.group(3) == "11"
    assert match.group(4) == "15.6954"

    match = CoordField._sexagesimal_letters.fullmatch("+17d59m59.876s")
    assert match.group(1) == "+17"
    assert match.group(2) == "d"
    assert match.group(3) == "59"
    assert match.group(4) == "59.876"

    invalid_strings = [
        "45h67.890s",
        "123d 45m 67",
        "123h 45m .890",
        "123hd 45m .890s",
        "123HH 45m .890s",
        "123h 45mM .890s",
        "123h 45m .890sS",
        "123dh 45m .890s",
        "67.890",
        "123",
        "123dm",
        "123d",
        "123dms",
        "123d45m67.s",
        "123d456m67s",
        "123d45m678s",
        "dms",
        " ",
        "",
    ]

    for s in invalid_strings:
        assert CoordField._sexagesimal_letters.fullmatch(s) is None


def test_angle_decimal_unit_regex():
    from lick_archive.apps.query.fields import CoordField

    match = CoordField._decimal_unit.fullmatch("+1.23456")
    assert match is not None
    assert match.group(1) == "+1.23456"
    assert match.group(2) == ""

    match = CoordField._decimal_unit.fullmatch("-12.3456M")
    assert match is not None
    assert match.group(1) == "-12.3456"
    assert match.group(2) == "M"

    match = CoordField._decimal_unit.fullmatch("-123")
    assert match is not None
    assert match.group(1) == "-123"
    assert match.group(2) == ""

    match = CoordField._decimal_unit.fullmatch("123D")
    assert match is not None
    assert match.group(1) == "123"
    assert match.group(2) == "D"

    match = CoordField._decimal_unit.fullmatch(".123s")
    assert match is not None
    assert match.group(1) == ".123"
    assert match.group(2) == "s"

    match = CoordField._decimal_unit.fullmatch(".123")
    assert match is not None
    assert match.group(1) == ".123"
    assert match.group(2) == ""

    match = CoordField._decimal_unit.fullmatch("0.123S")
    assert match is not None
    assert match.group(1) == "0.123"
    assert match.group(2) == "S"

    match = CoordField._decimal_unit.fullmatch("-.123H")
    assert match is not None
    assert match.group(1) == "-.123"
    assert match.group(2) == "H"

    # Below are examples from the simbad coordinate query page
    match = CoordField._decimal_unit.fullmatch("12.34567h")
    assert match.group(1) == "12.34567"
    assert match.group(2) == "h"

    match = CoordField._decimal_unit.fullmatch("-17.87654d")
    assert match.group(1) == "-17.87654"
    assert match.group(2) == "d"

    match = CoordField._decimal_unit.fullmatch("350.123456d")
    assert match.group(1) == "350.123456"
    assert match.group(2) == "d"

    match = CoordField._decimal_unit.fullmatch("350.123456")
    assert match.group(1) == "350.123456"
    assert match.group(2) == ""

    invalid_strings = [
        "m",
        "D",
        ".",
        ".h",
        ". h",
        "-",
        "-.",
        "-.S",
        "3-",
        "3.333.3",
        "3.333hm",
        "+-3.3",
        "3.",
        "-3.",
        " ",
        "",
    ]

    for s in invalid_strings:
        assert CoordField._decimal_unit.fullmatch(s) is None
