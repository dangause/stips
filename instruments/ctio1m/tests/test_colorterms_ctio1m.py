"""The Y4KCam colour-term library carries the literature transformations.

Stack-free: execs ``configs/colorterms.py`` against stand-ins for the LSST
``Colorterm``/``ColortermDict`` classes and checks the PS1 block holds the
Tonry et al. 2012 PS1 -> Johnson-Cousins terms in the sign convention the
stack applies (m = primary + c0 + c1 (p - s) + c2 (p - s)^2), and that the
profile declares the bands calibrated through it as Vega.
"""

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


def test_ps1_block_only(library):
    # PS1 is the only reference the terms are derived for; gaia/MONSTER modes
    # must find no block and run with colour terms off (see the gate tests).
    assert set(library) == {"ps1*"}
    assert set(library["ps1*"].data) == {"B", "V", "R", "I"}


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
    assert profile.vega_bands == {"gaia_ps1": ("r", "i")}
    # The Vega bands are exactly the ones the PS1 band map can calibrate.
    assert set(profile.vega_bands["gaia_ps1"]) == set(profile.ps1_band_map)
