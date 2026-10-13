"""lsst.obs.stips.binding: nameplates bind a profile onto the generic classes."""

import importlib
import sys
from pathlib import Path

import pytest

# Needs the real LSST stack (lsst.obs.base); skip cleanly in a plain venv.
pytest.importorskip("lsst.obs.base")

DATA = Path(__file__).parent / "data"
FIX = DATA / "instruments" / "demo_instrument"
FIX_CAM = DATA / "instruments" / "demo_camera_instrument"


@pytest.fixture(autouse=True)
def _fixture_root_importable():
    """The fixtures live under tests/data/instruments/; make that root importable
    and drop the cached shim so each test resolves INSTRUMENT_DIR afresh."""
    if str(DATA) not in sys.path:
        sys.path.append(str(DATA))
    yield
    sys.modules.pop("lsst.obs.stips.active", None)


def test_nameplate_binds_profile_with_its_own_class_path():
    from lsst.utils.introspection import get_full_type_name

    m = importlib.import_module("instruments.demo_instrument.instrument")
    assert m.Instrument.getName() == "DemoFix"
    assert (
        get_full_type_name(m.Instrument)
        == "instruments.demo_instrument.instrument.Instrument"
    )
    assert (
        get_full_type_name(m.RawFormatter)
        == "instruments.demo_instrument.instrument.RawFormatter"
    )
    assert m.Instrument.instrumentDir == FIX.resolve()
    assert m.Translator.name == "DemoFix"
    assert m.Instrument.translatorClass is m.Translator
    assert m.RawFormatter.instrumentClass is m.Instrument
    assert m.Instrument().getRawFormatter({}) is m.RawFormatter
    assert len(m.Instrument.filterDefinitions) >= 1


def test_camera_spec_profile_builds_camera_end_to_end():
    import lsst.afw.cameraGeom as cg
    import lsst.geom as geom

    m = importlib.import_module("instruments.demo_camera_instrument.instrument")
    cam = m.Instrument().getCamera()
    assert isinstance(cam, cg.Camera)
    dets = list(cam)
    assert len(dets) == 1
    assert dets[0].getBBox().getMax() == geom.Point2I(1024, 1024)


def test_bind_rejects_a_non_nameplate_module():
    from lsst.obs.stips.binding import bind

    with pytest.raises(ValueError, match="instrument.py"):
        bind("instruments.demo_instrument.profile")


def test_active_shim_reexports_the_nameplate_classes(monkeypatch):
    monkeypatch.setenv("INSTRUMENT_DIR", str(FIX))
    sys.modules.pop("lsst.obs.stips.active", None)
    active = importlib.import_module("lsst.obs.stips.active")
    m = importlib.import_module("instruments.demo_instrument.instrument")
    assert active.Instrument is m.Instrument
    assert active.Translator is m.Translator
    assert active.RawFormatter is m.RawFormatter


def test_active_shim_without_instrument_dir_fails_loud(monkeypatch):
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    sys.modules.pop("lsst.obs.stips.active", None)
    with pytest.raises(RuntimeError, match="INSTRUMENT_DIR"):
        importlib.import_module("lsst.obs.stips.active")


def test_package_import_without_instrument_dir_is_safe(monkeypatch):
    monkeypatch.delenv("INSTRUMENT_DIR", raising=False)
    import lsst.obs.stips  # must NOT trigger binding / raise

    assert hasattr(lsst.obs.stips, "StipsInstrument")
