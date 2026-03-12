"""Tests for Nickel instrument implementation."""

import pytest


class TestNickelInstrument:
    def test_name(self):
        from lsst.obs.smalltel.nickel.instrument import Nickel

        assert Nickel.getName() == "Nickel"

    def test_is_generic_small_tel(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument
        from lsst.obs.smalltel.nickel.instrument import Nickel

        assert issubclass(Nickel, GenericSmallTelInstrument)

    def test_camera_single_ccd(self):
        try:
            import lsst.obs.base  # noqa: F401
        except ImportError:
            pytest.skip("LSST stack not available")
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        camera = inst.getCamera()
        assert len(camera) == 1

    def test_filter_definitions(self):
        try:
            import lsst.obs.base  # noqa: F401
        except ImportError:
            pytest.skip("LSST stack not available")
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        names = {f.physical_filter for f in inst.filterDefinitions}
        assert {"B", "V", "R", "I", "clear"}.issubset(names)

    def test_get_raw_formatter(self):
        try:
            import lsst.obs.base  # noqa: F401
        except ImportError:
            pytest.skip("LSST stack not available")
        from lsst.obs.smalltel.nickel.instrument import Nickel

        inst = Nickel()
        fmt_cls = inst.getRawFormatter({})
        assert fmt_cls is not None
        assert "NickelRawFormatter" in fmt_cls.__name__


class TestPackageImports:
    def test_import_from_package_root(self):
        from lsst.obs.smalltel import Nickel, NickelTranslator

        assert Nickel.getName() == "Nickel"
        assert NickelTranslator.supported_instrument == "Nickel"

    def test_import_from_nickel_subpackage(self):
        from lsst.obs.smalltel.nickel import Nickel, NickelTranslator

        assert Nickel is not None
        assert NickelTranslator is not None

    def test_import_base_classes(self):
        from lsst.obs.smalltel.base_instrument import GenericSmallTelInstrument
        from lsst.obs.smalltel.base_translator import ConfigurableTranslator

        assert GenericSmallTelInstrument is not None
        assert ConfigurableTranslator is not None
