"""Tests for NickelTranslator — Nickel-specific method overrides."""


class TestNickelTranslator:
    def _make_translator(self, extra_headers=None):
        from lsst.obs.smalltel.nickel.translator import NickelTranslator

        header = {
            "INSTRUME": "Nickel Direct Imager",
            "EXPTIME": 60.0,
            "OBJECT": "2023ixf",
            "OBSTYPE": "object",
            "FILTNAM": "R",
            "OBSNUM": 42,
            "DATE-OBS": "2023-05-20T05:30:00",
            "DATE-END": "2023-05-20T05:31:00",
            "RA": "14:03:38.58",
            "DEC": "+54:18:42.1",
            "CRVAL1": 210.9108,
            "CRVAL2": 54.3117,
            "AIRMASS": 1.2,
        }
        if extra_headers:
            header.update(extra_headers)
        return NickelTranslator(header)

    def test_can_translate(self):
        from lsst.obs.smalltel.nickel.translator import NickelTranslator

        assert NickelTranslator.can_translate({"INSTRUME": "Nickel Direct Imager"})
        assert not NickelTranslator.can_translate({"INSTRUME": "LRIS"})

    def test_to_instrument(self):
        t = self._make_translator()
        assert t.to_instrument() == "Nickel"

    def test_to_exposure_id_range(self):
        t = self._make_translator()
        eid = t.to_exposure_id()
        assert 0 < eid < 2**31

    def test_to_visit_id_equals_exposure_id(self):
        t = self._make_translator()
        assert t.to_visit_id() == t.to_exposure_id()

    def test_to_day_obs(self):
        t = self._make_translator()
        day = t.to_day_obs()
        assert day == 20230520  # UT date from DATE-END

    def test_to_observation_type_science(self):
        t = self._make_translator()
        assert t.to_observation_type() == "science"

    def test_to_observation_type_bias(self):
        t = self._make_translator({"OBSTYPE": "dark", "OBJECT": "bias"})
        assert t.to_observation_type() == "bias"

    def test_to_observation_type_flat(self):
        t = self._make_translator({"OBSTYPE": "flat", "OBJECT": "domeflat"})
        assert t.to_observation_type() == "flat"

    def test_to_physical_filter(self):
        t = self._make_translator()
        assert t.to_physical_filter() == "R"

    def test_to_physical_filter_open(self):
        t = self._make_translator({"FILTNAM": "OPEN"})
        assert t.to_physical_filter() == "clear"

    def test_to_physical_filter_unknown_falls_back_to_clear(self):
        """Nickel convention: unknown filters map to 'clear'."""
        t = self._make_translator({"FILTNAM": "EXOTIC"})
        assert t.to_physical_filter() == "clear"

    def test_to_tracking_radec_crval(self):
        """When CRVAL and RA/DEC agree, use CRVAL."""
        t = self._make_translator()
        coord = t.to_tracking_radec()
        assert abs(coord.ra.deg - 210.91) < 0.1
        assert abs(coord.dec.deg - 54.31) < 0.1

    def test_to_tracking_radec_stuck_dec(self):
        """When CRVAL2 disagrees with DEC by >1 deg, use RA/DEC."""
        t = self._make_translator({"CRVAL2": 30.0})
        coord = t.to_tracking_radec()
        # Should fall back to RA/DEC headers
        assert abs(coord.dec.deg - 54.31) < 0.1
