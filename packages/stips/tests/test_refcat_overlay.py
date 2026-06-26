"""The gaia_ps1 calibrateImage overlay sets the right refcat fields.

Execs the config snippet against a mock ``config`` so we verify its assignments
without the LSST stack.
"""

from pathlib import Path
from unittest.mock import MagicMock

OVERLAY = (
    Path(__file__).resolve().parents[2]
    / "obs_stips/instrument_defaults/configs/refcats_gaia_ps1.py"
)


def test_gaia_ps1_overlay_sets_refcats():
    config = MagicMock()
    ns = {"config": config, "__file__": str(OVERLAY)}
    exec(compile(OVERLAY.read_text(), str(OVERLAY), "exec"), ns)

    # Astrometry -> Gaia DR3 (single-flux)
    assert config.connections.astrometry_ref_cat == "gaia_dr3"
    assert config.astrometry_ref_loader.anyFilterMapsToThis == "phot_g_mean"
    assert config.astrometry_ref_loader.filterMap == {}
    # Mag-limit flux field must be overridden off the MONSTER column.
    assert config.astrometry.referenceSelector.magLimit.fluxField == "phot_g_mean_flux"

    # Photometry -> PS1 DR2 + color terms
    assert config.connections.photometry_ref_cat == "panstarrs1_dr2"
    assert config.photometry.applyColorTerms is True
    assert config.photometry.photoCatName == "ps1"
    fmap = config.photometry_ref_loader.filterMap
    assert fmap["r"] == "rMeanPSFMag" and fmap["i"] == "iMeanPSFMag"
    assert fmap["b"] == "gMeanPSFMag" and fmap["v"] == "gMeanPSFMag"
    config.photometry.colorterms.load.assert_called_once()


def test_overlay_compiles():
    compile(OVERLAY.read_text(), str(OVERLAY), "exec")
