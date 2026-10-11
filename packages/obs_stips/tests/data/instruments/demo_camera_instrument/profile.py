"""Minimal fixture instrument profile whose camera is a CameraSpec (no yaml)."""

from stips import CameraSpec, Field, InstrumentProfile, Site

profile = InstrumentProfile(
    name="DemoCam",
    site=Site(10.0, 20.0, 100.0),
    filters={"B": "b", "clear": None},
    filter_aliases={"B": "B", "OPEN": "clear"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera=CameraSpec(
        nx=1024,
        ny=1024,
        pixel_size_um=30.0,
        plate_scale_arcsec_per_pixel=0.368,
        flip_y=True,
    ),
    filter_key="FILTNAM",
)
