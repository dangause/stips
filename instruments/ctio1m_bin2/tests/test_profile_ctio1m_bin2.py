"""The 2x2-binned Y4KCam variant: same camera, its own Butler identity."""

from pathlib import Path

from stips.core.config import load_active_profile
from stips.profile import instrument_class_for

_DIR = Path(__file__).resolve().parents[1]
_BASE = _DIR.parent / "ctio1m"


def test_identity_and_binning():
    prof = load_active_profile(_DIR)
    base = load_active_profile(_BASE)
    assert prof.name == "CTIO1m_bin2"
    assert prof.collection_prefix == "CTIO1m_bin2"
    assert prof.policy_name == "CTIO1m_bin2"
    assert prof.ccd_binning == 2
    assert prof.binning_header == "CCDSUM"
    assert instrument_class_for(_DIR) == "instruments.ctio1m_bin2.instrument.Instrument"
    # Shared with the base: camera description, filters, crosstalk, skymap.
    assert prof.camera == base.camera
    assert prof.filters == base.filters
    assert prof.crosstalk is base.crosstalk
    assert prof.skymap_name == base.skymap_name


def test_defects_off_and_no_data_package():
    prof = load_active_profile(_DIR)
    assert prof.obs_data_package is None
    assert prof.isr_overrides["doDefect"] is False
    assert prof.isr_overrides["overscan.doParallelOverscan"] is True


def test_hooks_are_a_copy_not_the_base_dict():
    prof = load_active_profile(_DIR)
    base = load_active_profile(_BASE)
    assert prof.hooks == base.hooks
    assert prof.hooks is not base.hooks


def test_shared_resources_resolve():
    assert (_DIR / "camera" / "y4kcam.yaml").is_file()
    assert (_DIR / "configs").is_dir()
