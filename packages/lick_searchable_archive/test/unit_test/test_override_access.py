from pathlib import Path

import pytest


def test_check_filename():
    from lick_archive.authorization.override_access import OverrideAccessFile

    matching_names = [
        "override.access",
        "override.1.access",
        "directory/override.12.access",
        Path("/directory/subdir/override.123.access"),
    ]

    not_matching_names = [
        "",
        "override",
        "overrideaccess",
        "unrelated.access",
        "override.1",
        "override.a.access",
        "override..access",
        "override.abcd.access",
        "Override.access",
        "#override.access",
        "override.2.access~",
        "override.3x.access",
    ]

    for name in matching_names:
        assert (
            OverrideAccessFile.check_filename(name) is True
        ), f"{name} was not considered an override access file"

    for name in not_matching_names:
        assert (
            OverrideAccessFile.check_filename(name) is False
        ), f"{name} was considered an override access file"


def test_obstype_access_rule():
    from lick_archive.authorization.override_access import OverrideAccessRule
    from lick_archive.metadata.data_dictionary import FrameType

    rule = OverrideAccessRule.from_str(
        "s1* access owner.hint1 owner@hint2 _ownerhint_3"
    )
    assert rule.pattern == "s1*"
    assert rule._patterns == ["s1*"]
    assert rule.obstype is None
    assert rule.ownerhints == ["owner.hint1", "owner@hint2", "_ownerhint_3"]

    assert rule.matches("/data/1970-01/01/AO/s1.fits")
    assert rule.matches("/data/1970-01/01/AO/s101.fits")
    assert rule.matches("s101a.1.fits")
    assert not rule.matches("s01.fits")

    rule = OverrideAccessRule.from_str("s1024*.fits obstype cal")
    assert rule.pattern == "s1024*.fits"
    assert rule._patterns == ["s1024*.fits"]
    assert rule.obstype == FrameType.calib
    assert rule.ownerhints == []

    assert rule.matches("/data/1970-01/01/AO/s1024.fits")
    assert rule.matches("/data/1970-01/01/AO/s1024.1.fits")
    assert rule.matches("/data/1970-01/01/AO/s10245.fits")

    rule = OverrideAccessRule.from_str("s1024.fits obstype cal")
    assert rule.pattern == "s1024.fits"
    assert rule._patterns == ["s1024.fits", "s1024.*.fits"]
    assert rule.obstype == FrameType.calib
    assert rule.ownerhints == []

    assert rule.matches("/data/1970-01/01/AO/s1024.fits")
    assert rule.matches("/data/1970-01/01/AO/s1024.1.fits")
    assert not rule.matches("/data/1970-01/01/AO/s10245.fits")

    with pytest.raises(ValueError):
        rule = OverrideAccessRule.from_str("s1024.fits invalid abcd")

    with pytest.raises(ValueError):
        rule = OverrideAccessRule.from_str("s1024.fits obstype")

    with pytest.raises(ValueError):
        rule = OverrideAccessRule.from_str("s1024.fits access")

    with pytest.raises(ValueError):
        rule = OverrideAccessRule.from_str("access")

    with pytest.raises(ValueError):
        rule = OverrideAccessRule.from_str("")


def test_from_file():
    test_data_dir = Path(__file__).parent / "test_data"
    subdir = "2012-01/18/shane"

    # Parsing of first override access file
    from datetime import date

    from lick_archive.authorization.override_access import OverrideAccessFile

    oaf = OverrideAccessFile.from_file(test_data_dir / subdir / "override.access")
    assert oaf.observing_night == date(year=2012, month=1, day=18)
    assert oaf.instrument_dir == "shane"
    assert oaf.sequence_id == 0
    assert len(oaf.override_rules) == 2
    assert oaf.override_rules[0].pattern == "r1234.fits"
    assert oaf.override_rules[1].pattern == "r[12]*"

    # Parsing of file with a sequence id
    oaf = OverrideAccessFile.from_file(
        str(test_data_dir / subdir / "override.1.access")
    )
    assert oaf.observing_night == date(year=2012, month=1, day=18)
    assert oaf.instrument_dir == "shane"
    assert oaf.sequence_id == 1
    assert len(oaf.override_rules) == 2
    assert oaf.override_rules[0].pattern == "r1234.fits"
    assert oaf.override_rules[1].pattern == "r[12]*"

    # Test emtpy file. I'm not sure if this should error but right now it doesn't
    oaf = OverrideAccessFile.from_file(
        str(test_data_dir / subdir / "override.2.access")
    )
    assert oaf.observing_night == date(year=2012, month=1, day=18)
    assert oaf.instrument_dir == "shane"
    assert oaf.sequence_id == 2
    assert len(oaf.override_rules) == 0

    # Test invalid filename
    with pytest.raises(ValueError):
        oaf = OverrideAccessFile.from_file(
            str(test_data_dir / subdir / "good_2012_01_18_r1002.fits")
        )


def test_matching_rules():
    test_data_dir = Path(__file__).parent / "test_data"
    subdir = "2012-01/18/shane"

    from lick_archive.authorization.override_access import (
        OverrideAccessFile,
        find_matching_rules,
    )

    oaf0 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.access")
    oaf1 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.1.access")
    oaf2 = OverrideAccessFile.from_file(test_data_dir / subdir / "override.2.access")

    # The way rule resolution works, this should hit the rule in override.1.access that sets the type to "arc"
    # import pdb; pdb.set_trace()
    matching_rule = find_matching_rules([oaf0, oaf1], "r1234.fits")

    from lick_archive.metadata.data_dictionary import FrameType

    assert matching_rule is not None
    assert matching_rule.pattern == "r1234.fits"
    assert matching_rule.obstype == FrameType.arc

    # The way rule resolution works, this should not hit the rule in override.access that sets the ownerhints,
    # but instead hit the rule in override.1.access
    matching_rule = find_matching_rules([oaf0, oaf1], "r12345.fits")
    assert matching_rule is not None
    assert matching_rule.pattern == "r[12]*"
    assert matching_rule.ownerhints == ["ownerhint3", "ownerhint4"]

    # The way rule resolution works, this should hit the first rule in override.access that sets the type to flat
    matching_rule = find_matching_rules([oaf0], "r1234.fits")
    assert matching_rule is not None
    assert matching_rule.pattern == "r1234.fits"
    assert matching_rule.obstype == FrameType.flat

    # Test something that doesn't match
    matching_rule = find_matching_rules([oaf0, oaf1, oaf2], "r3456.fits")
    assert matching_rule is None
