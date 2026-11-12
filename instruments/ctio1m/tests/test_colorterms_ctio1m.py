"""The Y4KCam colour-term library carries the literature transformations.

Stack-free: execs ``configs/colorterms.py`` against stand-ins for the LSST
``Colorterm``/``ColortermDict`` classes and checks the PS1 block holds the
Tonry et al. 2012 PS1 -> Johnson-Cousins terms in the sign convention the
stack applies (m = primary + c0 + c1 (p - s) + c2 (p - s)^2), and that the
profile declares the bands calibrated through it as Vega. Also checks the
Gaia DR3 block (a STIPS fit of Gaia AB magnitudes against Landolt standards
-- see ``scripts/analysis/fit_gaia_colorterms_landolt.py``), its Vega
declaration in ``gaia`` mode, and that its glob
resolves for the refcat name the ``gaia`` mode actually uses, mirroring the
lookup in ``packages/obs_stips/instrument_defaults/configs/
apply_colorterms.py`` (exact key, else exactly one matching glob).
"""

import fnmatch
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest
from stips.testing.instrument_contract import InstrumentDirInfo, load_profile

_INFO = InstrumentDirInfo(name="ctio1m", path=Path(__file__).resolve().parents[1])
_LIBRARY = _INFO.path / "configs" / "colorterms.py"


@dataclass
class _Colorterm:
    primary: str
    secondary: str
    c0: float
    c1: float
    c2: float


@dataclass
class _ColortermDict:
    data: dict


@pytest.fixture
def library(monkeypatch):
    """Exec the library file the way pex_config would, with stub classes."""
    stub = types.ModuleType("lsst.pipe.tasks.colorterms")
    stub.Colorterm, stub.ColortermDict = _Colorterm, _ColortermDict
    for name in ("lsst", "lsst.pipe", "lsst.pipe.tasks"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "lsst.pipe.tasks.colorterms", stub)
    config = types.SimpleNamespace()
    exec(compile(_LIBRARY.read_text(), str(_LIBRARY), "exec"), {"config": config})
    return config.data


def test_ps1_and_gaia_blocks_only(library):
    # PS1 and Gaia DR3 are the only references with fitted terms; MONSTER
    # mode must find no block and run with colour terms off (see the gate
    # tests in test_colorterm_gate.py).
    assert set(library) == {"ps1*", "gaia*"}
    assert set(library["ps1*"].data) == {"B", "V", "R", "I", "I_SOAR"}
    assert set(library["gaia*"].data) == {"B", "V", "R", "I", "I_SOAR"}


@pytest.mark.parametrize(
    ("band", "primary", "secondary", "c0", "c1", "c2"),
    [
        # Tonry et al. 2012 Table 6, x = g - r, verbatim for the g-primary bands.
        ("B", "gMeanPSFMag", "rMeanPSFMag", 0.212, 0.556, 0.034),
        ("V", "gMeanPSFMag", "rMeanPSFMag", 0.005, -0.536, 0.011),
        # Rc - r = -0.137 - 0.108 x - 0.029 x^2 with colour (r - g) = -x.
        ("R", "rMeanPSFMag", "gMeanPSFMag", -0.137, 0.108, -0.029),
        # Ic - i = -0.366 - 0.136 x, linearised on the locus x ~ 1.7 (r - i).
        ("I", "iMeanPSFMag", "rMeanPSFMag", -0.366, 0.23, 0.0),
        ("I_SOAR", "iMeanPSFMag", "rMeanPSFMag", -0.366, 0.23, 0.0),
    ],
)
def test_tonry_terms(library, band, primary, secondary, c0, c1, c2):
    term = library["ps1*"].data[band]
    assert (term.primary, term.secondary) == (primary, secondary)
    assert (term.c0, term.c1, term.c2) == pytest.approx((c0, c1, c2))


def test_r_term_matches_tonry_at_a_solar_colour(library):
    # Evaluate both forms at g - r = 0.45: Tonry gives Rc - r = -0.1915.
    x = 0.45
    tonry = -0.137 - 0.108 * x - 0.029 * x**2
    term = library["ps1*"].data["R"]
    colour = -x  # primary - secondary = r - g
    assert term.c0 + term.c1 * colour + term.c2 * colour**2 == pytest.approx(tonry)


def test_profile_declares_r_i_vega_in_gaia_ps1_mode():
    profile = load_profile(_INFO)
    assert profile.vega_bands["gaia_ps1"] == ("r", "i")
    # The Vega bands are exactly the ones the PS1 band map can calibrate.
    assert set(profile.vega_bands["gaia_ps1"]) == set(profile.ps1_band_map)


def test_profile_declares_bvri_vega_in_gaia_mode(library):
    # The gaia* terms are fitted from Gaia AB magnitudes onto Landolt (Vega)
    # magnitudes, so every band they calibrate comes out Vega; monster mode
    # has no colour terms and stays AB.
    profile = load_profile(_INFO)
    assert profile.vega_bands == {
        "gaia_ps1": ("r", "i"),
        "gaia": ("b", "v", "r", "i"),
    }
    # The Vega bands are exactly the bands the gaia* block reaches.
    gaia_bands = {profile.filters[f] for f in library["gaia*"].data}
    assert set(profile.vega_bands["gaia"]) == gaia_bands


@pytest.mark.parametrize(
    ("band", "primary", "secondary"),
    [
        ("B", "phot_bp_mean", "phot_rp_mean"),
        ("V", "phot_g_mean", "phot_rp_mean"),
        ("R", "phot_rp_mean", "phot_g_mean"),
        ("I", "phot_rp_mean", "phot_g_mean"),
        ("I_SOAR", "phot_rp_mean", "phot_g_mean"),
    ],
)
def test_gaia_terms_use_flux_column_primary_secondary_names(
    library, band, primary, secondary
):
    # The LSST Colorterm reads "<primary>_flux"/"<secondary>_flux" from the
    # reference catalogue; the Gaia refcat converted by stips_refcats has
    # phot_g_mean_flux, phot_bp_mean_flux, phot_rp_mean_flux, so the names
    # must be phot_g_mean/phot_bp_mean/phot_rp_mean, not the Nickel gaia*
    # block's "*_mag" names (which the catalogue lacks).
    term = library["gaia*"].data[band]
    assert (term.primary, term.secondary) == (primary, secondary)


@pytest.mark.parametrize(
    ("band", "c0", "c1"),
    [
        # 2026-11-07 fit on Gaia AB magnitudes (LSST converter zero points).
        ("B", 0.1694, 0.6532),
        ("V", -0.1148, 0.8007),
        ("R", -0.2295, -0.7236),
        ("I", -0.3942, 0.1387),
    ],
)
def test_gaia_terms_are_the_ab_fit(library, band, c0, c1):
    term = library["gaia*"].data[band]
    assert (term.c0, term.c1, term.c2) == pytest.approx((c0, c1, 0.0))


def test_gaia_c0_is_not_the_vega_fit(library):
    # The 2026-11-03 terms were fitted on Gaia Vega magnitudes; their c0
    # differed from the AB fit by the constant Vega-AB offsets (I by 0.40
    # mag). Guard against the Vega constants coming back.
    vega_c0 = {"B": -0.0016, "V": -0.2186, "R": -0.0510, "I": 0.0103}
    for band, old in vega_c0.items():
        assert abs(library["gaia*"].data[band].c0 - old) > 0.05


def test_gaia_i_soar_matches_i(library):
    i, i_soar = library["gaia*"].data["I"], library["gaia*"].data["I_SOAR"]
    assert (i_soar.primary, i_soar.secondary, i_soar.c0, i_soar.c1, i_soar.c2) == (
        i.primary,
        i.secondary,
        i.c0,
        i.c1,
        i.c2,
    )


def test_gaia_block_resolves_for_gaia_dr3_refcat(library):
    # Same lookup as apply_colorterms.py: the refcat name is aliased
    # ("gaia_dr3" -> "gaia") before matching library keys by exact name or
    # exactly one glob.
    refname = "gaia_dr3"
    alias = {
        "panstarrs1_dr2": "ps1",
        "gaia_dr3": "gaia",
        "the_monster_20250219_local": "monster",
    }
    photo_cat_name = alias.get(refname, refname)
    matches = [glob for glob in library if fnmatch.fnmatch(photo_cat_name, glob)]
    assert matches == ["gaia*"]
