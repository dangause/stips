"""The gaia_ps1 calibrateImage overlays set the right refcat fields.

Execs the config snippets against a mock ``config`` so we verify their
assignments without the LSST stack. Two overlays exist post-tiering (F-012):

* the NEUTRAL framework default (``instrument_defaults/configs/``), which
  derives its PS1 filterMap from the active profile's ``ps1_band_map`` (via
  $INSTRUMENT_DIR) and enables color terms only for a non-empty library; and
* the reference NICKEL overlay (``instruments/nickel/configs/``), which shadows
  it instrument-dir-first and carries the full hand-written Nickel band map +
  Landolt color terms.
"""

from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parents[3]
NEUTRAL_OVERLAY = (
    _REPO_ROOT / "packages/obs_stips/instrument_defaults/configs/refcats_gaia_ps1.py"
)
NICKEL_OVERLAY = _REPO_ROOT / "instruments/nickel/configs/refcats_gaia_ps1.py"
CTIO1M_DIR = _REPO_ROOT / "instruments/ctio1m"


def _exec_overlay(overlay: Path) -> MagicMock:
    config = MagicMock()
    ns = {"config": config, "__file__": str(overlay)}
    exec(compile(overlay.read_text(), str(overlay), "exec"), ns)
    return config


def _assert_gaia_astrometry(config: MagicMock) -> None:
    # Astrometry -> Gaia DR3 (single-flux)
    assert config.connections.astrometry_ref_cat == "gaia_dr3"
    assert config.astrometry_ref_loader.anyFilterMapsToThis == "phot_g_mean"
    assert config.astrometry_ref_loader.filterMap == {}
    # Mag-limit flux field must be overridden off the MONSTER column.
    assert config.astrometry.referenceSelector.magLimit.fluxField == "phot_g_mean_flux"


def test_neutral_overlay_derives_filtermap_from_profile(monkeypatch):
    """The neutral overlay derives its PS1 filterMap from profile.ps1_band_map."""
    monkeypatch.setenv("INSTRUMENT_DIR", str(CTIO1M_DIR))
    config = _exec_overlay(NEUTRAL_OVERLAY)

    _assert_gaia_astrometry(config)

    # Photometry -> PS1 DR2; map derived from ctio1m's ps1_band_map ({r: r, i: i})
    assert config.connections.photometry_ref_cat == "panstarrs1_dr2"
    assert config.photometry.photoCatName == "ps1"
    assert config.photometry_ref_loader.filterMap == {
        "r": "rMeanPSFMag",
        "i": "iMeanPSFMag",
    }
    # ctio1m ships no configs/colorterms.py, so the neutral (empty) library is
    # loaded and color terms stay OFF (len(MagicMock) == 0 mirrors the empty lib).
    config.photometry.colorterms.load.assert_called_once()
    loaded_path = Path(config.photometry.colorterms.load.call_args[0][0])
    assert loaded_path == NEUTRAL_OVERLAY.parent / "colorterms.py"
    assert config.photometry.applyColorTerms is False


def test_nickel_overlay_sets_refcats():
    """The Nickel overlay keeps the full hand-written band map + color terms ON."""
    config = _exec_overlay(NICKEL_OVERLAY)

    _assert_gaia_astrometry(config)

    # Photometry -> PS1 DR2 + Landolt color terms
    assert config.connections.photometry_ref_cat == "panstarrs1_dr2"
    assert config.photometry.applyColorTerms is True
    assert config.photometry.photoCatName == "ps1"
    fmap = config.photometry_ref_loader.filterMap
    assert fmap["r"] == "rMeanPSFMag" and fmap["i"] == "iMeanPSFMag"
    assert fmap["b"] == "gMeanPSFMag" and fmap["v"] == "gMeanPSFMag"
    # The co-located Nickel colorterms.py (moved in the F-012 tiering) is loaded.
    config.photometry.colorterms.load.assert_called_once()
    loaded_path = Path(config.photometry.colorterms.load.call_args[0][0])
    assert loaded_path == NICKEL_OVERLAY.parent / "colorterms.py"


def test_overlays_compile():
    for overlay in (NEUTRAL_OVERLAY, NICKEL_OVERLAY):
        compile(overlay.read_text(), str(overlay), "exec")
