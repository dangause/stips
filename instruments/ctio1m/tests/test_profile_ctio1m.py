"""Stack-free tests for the CTIO 1.0m Y4KCam profile + hooks."""

from conftest import load_ctio1m_profile


def test_identity():
    prof = load_ctio1m_profile()
    assert prof.name == "CTIO1m"
    assert prof.collection_prefix == "CTIO1m"
    assert prof.instrument_class == "lsst.obs.stips.active.Instrument"
    assert prof.filter_key == "FILTERID"


def test_filters_broadband():
    prof = load_ctio1m_profile()
    for phys, band in [("V", "v"), ("B", "b"), ("R", "r"), ("I", "i")]:
        assert prof.filters.get(phys) == band


def test_filter_aliases_map_raw_filterid():
    prof = load_ctio1m_profile()
    assert prof.filter_aliases.get("V") == "V"
    assert prof.filter_aliases.get("B") == "B"


def test_camera_is_yaml_path():
    prof = load_ctio1m_profile()
    assert prof.camera == "camera/y4kcam.yaml"
