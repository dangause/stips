"""Minimal fixture instrument profile for profile_loader tests."""

from stips import Field, InstrumentProfile, Site

profile = InstrumentProfile(
    name="DemoFix",
    site=Site(10.0, 20.0, 100.0),
    filters={"B": "b", "clear": None},
    filter_aliases={"B": "B", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera="camera/demo.yaml",
    filter_key="FILTNAM",
)
