# tests/test_translator.py
import unittest

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time

from lsst.obs.nickel.translator import NickelTranslator


class TestNickelTranslator(unittest.TestCase):
    def setUp(self):
        # Minimal dict distilled from the header you provided; includes all
        # keys the final translator actually uses.
        self.header = {
            # IDs / instrument
            "INSTRUME": "Nickel Direct Camera",
            "OBSNUM": 1032,

            # Times
            "EXPTIME": 120.0,
            "DATE-BEG": "2024-06-25T05:15:49.25",
            "DATE-END": "2024-06-25T05:17:49.25",

            # WCS center (primary; degrees)
            "CRVAL1": 179.1170349121,
            "CRVAL2": 55.1252822876,
            "CRPIX1": 512.0,
            "CRPIX2": 512.0,
            "CUNIT1": "deg",
            "CUNIT2": "deg",
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
            "RADECSYS": "FK5",
            "EQUINOX": 2000.0,

            # Misc used by trivial map and sanity checks
            "OBJECT": "NGC_3982",
            "AIRMASS": 1.281367778778,
            "TEMPDET": -109.7,
            "FILTNAM": "B",
            "TELESCOP": "Nickel 1m",  # not required by can_translate, but realistic
        }
        self.tr = NickelTranslator(self.header)

    def test_can_translate(self):
        self.assertTrue(NickelTranslator.can_translate(self.header))

    def test_datetime_begin(self):
        t0 = self.tr.to_datetime_begin()
        self.assertIsInstance(t0, Time)
        self.assertAlmostEqual(
            t0.mjd,
            Time("2024-06-25T05:15:49.25", format="isot", scale="utc").mjd,
            places=9,
        )

    def test_datetime_end(self):
        t1 = self.tr.to_datetime_end()
        self.assertIsInstance(t1, Time)
        self.assertAlmostEqual(
            t1.mjd,
            Time("2024-06-25T05:17:49.25", format="isot", scale="utc").mjd,
            places=9,
        )

        # Fallback: no DATE-END -> begin + EXPTIME
        hdr = dict(self.header)
        hdr.pop("DATE-END")
        tr2 = NickelTranslator(hdr)
        t1b = tr2.to_datetime_end()
        expected = Time(hdr["DATE-BEG"], format="isot", scale="utc") + hdr["EXPTIME"] * u.s
        self.assertAlmostEqual(t1b.mjd, expected.mjd, places=9)

    def test_temperature(self):
        # -109.7 C -> 163.45 K
        self.assertAlmostEqual(self.tr.to_temperature().to_value(u.K), 163.45, places=2)

    def test_airmass(self):
        # Keep translator precision; compare to 2 dp per your earlier expectation
        self.assertAlmostEqual(self.tr.to_boresight_airmass(), 1.28, places=2)

    def test_tracking_radec_from_primary_wcs(self):
        coord = self.tr.to_tracking_radec()
        self.assertIsInstance(coord, SkyCoord)
        expected = SkyCoord(self.header["CRVAL1"], self.header["CRVAL2"], unit=u.deg, frame="fk5")
        # Compare by separation (< 0.1 arcsec)
        sep = coord.separation(expected).to(u.arcsec).value
        self.assertLess(sep, 0.1)

    def test_physical_filter(self):
        # Translator returns FILTNAM as-is, stripped.
        self.assertEqual(self.tr.to_physical_filter(), "B")

    def test_observation_type_and_reason(self):
        self.assertEqual(self.tr.to_observation_type(), "science")
        self.assertEqual(self.tr.to_observation_reason(), "science")

        # Quick calibration cases (via OBJECT content)
        hdr = dict(self.header)
        hdr["OBJECT"] = "twilight flat"
        tr2 = NickelTranslator(hdr)
        self.assertEqual(tr2.to_observation_type(), "flat")
        self.assertEqual(tr2.to_observation_reason(), "calibration")

    def test_ids_and_detector_fields(self):
        self.assertEqual(self.tr.to_instrument(), "Nickel")
        self.assertEqual(self.tr.to_exposure_id(), 1032)
        self.assertEqual(self.tr.to_visit_id(), 1032)
        self.assertEqual(self.tr.to_detector_num(), 0)
        self.assertEqual(self.tr.to_detector_name(), "0")
        self.assertEqual(self.tr.to_detector_unique_name(), "0")
        self.assertEqual(self.tr.to_detector_serial(), "")
        self.assertEqual(self.tr.to_detector_group(), "")
        self.assertEqual(self.tr.to_detector_exposure_id(), 1032)

    def test_location(self):
        loc = self.tr.to_location()
        # EarthLocation.of_site("Lick Observatory") — allow small tolerance
        self.assertTrue(hasattr(loc, "lat") and hasattr(loc, "lon"))
        self.assertAlmostEqual(loc.lat.deg, 37.34, places=2)
        self.assertAlmostEqual(loc.lon.deg, -121.64, places=2)

    def test_altaz_and_pressure(self):
        self.assertIsNone(self.tr.to_altaz_begin())
        self.assertIsNone(self.tr.to_pressure())


if __name__ == "__main__":
    unittest.main()
