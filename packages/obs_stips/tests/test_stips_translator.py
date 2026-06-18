import unittest

from lsst.obs.stips.translator import StipsTranslator
from stips import Field, InstrumentProfile, Site, hook

PROFILE = InstrumentProfile(
    name="Demo",
    site=Site(10.0, 20.0, 100.0),
    filters={"B": "B", "OPEN": "clear"},
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


class TestStipsTranslator(unittest.TestCase):
    def test_can_translate_matches_name(self):
        self.assertTrue(DemoTranslator.can_translate({"INSTRUME": "Demo cam"}))
        self.assertFalse(DemoTranslator.can_translate({"INSTRUME": "Other"}))

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
            .asDegrees(),
            0.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
