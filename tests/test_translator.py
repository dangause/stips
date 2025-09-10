import unittest
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u

from lsst.obs.nickel.translator import NickelTranslator


class TestNickelTranslator(unittest.TestCase):

    def setUp(self):
        self.header = {
            "SIMPLE": True,
            "BITPIX": 16,
            "NAXIS": 2,
            "NAXIS1": 1056,
            "NAXIS2": 1024,
            "OBSNUM": 1032,
            "OBSTYPE": "OBJECT",
            "EXPTIME": 120.0,
            "PROGRAM": "NEWCAM",
            "VERSION": "nickel_direct",
            "DATE": "2024-06-25T05:17:49.85",
            "DATASEC": "[1:1024,1:1024]",
            "CRDER2": 5.139999848325e-05,
            "CRDER1": 5.139999848325e-05,
            "CD2_2": -0.0001027239995892,
            "CD2_1": 3.946270226152e-06,
            "CD1_2": -3.946270226152e-06,
            "CD1_1": -0.0001027239995892,
            "CRVAL2": 55.1252822876,         
            "CRVAL1": 179.1170349121,        
            "CRPIX2": 512.0,
            "CRPIX1": 512.0,
            "CUNIT2": "deg",
            "CUNIT1": "deg",
            "EQUINOX": 2000.0,
            "RADECSYS": "FK5",
            "CNAME2": "Declination",
            "CNAME1": "Right Ascension",
            "CTYPE2": "DEC--TAN",
            "CTYPE1": "RA---TAN",
            "AIRMASS": 1.281367778778,
            "HA": "03:28:47.89",
            "DEC": "55:07:31.0",
            "RA": "11:56:28.09",
            "DATE-BEG": "2024-06-25T05:15:49.25",
            "INSTRUME": "Nickel Direct Camera",
            "FILTNAM": "B",
            "TEMPDET": -109.7,
            "OBJECT": "NGC_3982",
        }
        self.translator = NickelTranslator(self.header)

    def test_can_translate(self):
        self.assertTrue(NickelTranslator.can_translate(self.header))

    def test_datetime_begin(self):
        dt = self.translator.to_datetime_begin()
        self.assertIsInstance(dt, Time)
        self.assertAlmostEqual(
            dt.mjd,
            Time("2024-06-25T05:15:49.25", format="isot", scale="utc").mjd,
            places=6,
        )


    def test_temperature(self):
        temp = self.translator.to_temperature()
        self.assertAlmostEqual(temp.to_value(u.K), 163.45, places=2)

    def test_tracking_radec(self):
        coord = self.translator.to_tracking_radec()
        self.assertIsInstance(coord, SkyCoord)
        self.assertAlmostEqual(coord.ra.hour, 11 + 56/60 + 28.09/3600, places=4)
        self.assertAlmostEqual(coord.dec.degree, 55 + 7/60 + 31.0/3600, places=4)

    def test_exposure_id(self):
        self.assertEqual(self.translator.to_exposure_id(), 1032)

    def test_physical_filter(self):
        self.assertEqual(self.translator.to_physical_filter(), "B")

    def test_airmass(self):
        self.assertAlmostEqual(self.translator.to_boresight_airmass(), 1.28, places=2)

    def test_object(self):
        self.assertEqual(self.translator.to_object(), "NGC_3982")

    def test_observation_type(self):
        self.assertEqual(self.translator.to_observation_type(), "science")


if __name__ == "__main__":
    unittest.main()
