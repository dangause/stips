import unittest

import astropy.units as u
import pytest

pytest.importorskip("lsst.obs.stips")

from lsst.obs.stips.translator import StipsTranslator  # noqa: E402
from stips import Field, InstrumentProfile, Site, hook  # noqa: E402

PROFILE = InstrumentProfile(
    name="Demo",
    site=Site(10.0, 20.0, 100.0),
    filters={"B": "b", "clear": None},
    filter_aliases={"B": "B", "OPEN": "clear"},
    header_map={
        "exposure_time": Field("EXPTIME", unit="s", default=0.0),
        "telescope": Field("TELESCOP", default="Demo 1m"),
    },
    const_map={
        "boresight_rotation_angle": 0.0,
        "boresight_rotation_coord": "sky",
    },
    camera="camera/demo.yaml",
    filter_key="FILTNAM",
)


@hook(PROFILE)
def unknown_filter(header, raw):
    return "clear"


class DemoTranslator(StipsTranslator):
    profile = PROFILE


# A profile whose instrument name differs from the FITS INSTRUME value (e.g.
# CTIO1m / Y4KCam) and that provides a day_obs hook — exercises the
# instrument_header_value match and the to_observing_day hook wiring.
HDRVAL_PROFILE = InstrumentProfile(
    name="FooScope",
    instrument_header_value="BarCam",
    site=Site(10.0, 20.0, 100.0),
    filters={"B": "b"},
    filter_aliases={"B": "B"},
    header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
    const_map={"boresight_rotation_angle": 0.0, "boresight_rotation_coord": "sky"},
    camera="camera/foo.yaml",
    filter_key="FILTNAM",
)


@hook(HDRVAL_PROFILE)
def day_obs(header):
    return int(str(header["DTCALDAT"]).replace("-", ""))


class HdrValTranslator(StipsTranslator):
    profile = HDRVAL_PROFILE


class TestStipsTranslator(unittest.TestCase):
    def test_can_translate_matches_name(self):
        self.assertTrue(DemoTranslator.can_translate({"INSTRUME": "Demo cam"}))
        self.assertFalse(DemoTranslator.can_translate({"INSTRUME": "Other"}))

    def test_can_translate_uses_instrument_header_value(self):
        # When the instrument name differs from INSTRUME, can_translate matches
        # the profile's instrument_header_value, NOT its name.
        self.assertTrue(HdrValTranslator.can_translate({"INSTRUME": "BarCam"}))
        self.assertFalse(HdrValTranslator.can_translate({"INSTRUME": "FooScope"}))

    def test_observing_day_uses_day_obs_hook(self):
        # The Butler day_obs dimension comes from to_observing_day; a profile's
        # day_obs hook must actually drive it (regression for the dead to_day_obs).
        self.assertEqual(
            HdrValTranslator(
                {"INSTRUME": "BarCam", "DTCALDAT": "2007-03-21"}
            ).to_observing_day(),
            20070321,
        )

    def test_known_filter_from_map(self):
        self.assertEqual(
            DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "B"}).to_physical_filter(),
            "B",
        )

    def test_unknown_filter_uses_hook(self):
        self.assertEqual(
            DemoTranslator({"INSTRUME": "Demo", "FILTNAM": "ZZ"}).to_physical_filter(),
            "clear",
        )

    def test_location_geodetic(self):
        loc = DemoTranslator({"INSTRUME": "Demo"}).to_location()
        self.assertAlmostEqual(loc.lat.deg, 10.0, places=6)

    def test_telescope_trivial_default(self):
        self.assertEqual(DemoTranslator({"INSTRUME": "Demo"}).to_telescope(), "Demo 1m")

    def test_boresight_rotation_from_const_map(self):
        self.assertAlmostEqual(
            DemoTranslator({"INSTRUME": "Demo"})
            .to_boresight_rotation_angle()
            .to_value(u.deg),
            0.0,
            places=6,
        )

    def test_pressure_defaults_to_none(self):
        # Small-telescope headers carry no barometric pressure; the generic
        # translator must still satisfy ObservationInfo by returning None
        # (rather than the base FitsTranslator's NotImplementedError).
        self.assertIsNone(DemoTranslator({"INSTRUME": "Demo"}).to_pressure())

    def test_altaz_begin_defaults_to_none(self):
        # Not in the headers; mirrors the base to_altaz_end (also None).
        self.assertIsNone(DemoTranslator({"INSTRUME": "Demo"}).to_altaz_begin())


if __name__ == "__main__":
    unittest.main()
