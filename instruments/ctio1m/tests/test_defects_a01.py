"""Stack-free checks on the CTIO curated defect ECSVs.

Amp A01 was hardware-dead across the entire 2010 SA98 run but healthy in 2006
NGC2298 (finding f9d24bb) -- so the mask is EPOCH-SCOPED, not a geometry change.
An empty pre-2010 base defect masks nothing (2006 keeps all four amps); a
2010-epoch defect masks the dead A01 quadrant (assembled box 2032,0,2032,2032).
Butler selects the most-recent-valid defect per exposure, giving the scoping.
"""

from pathlib import Path

from astropy.table import Table

_D = (
    Path(__file__).resolve().parents[1]
    / "obs_ctio1m_data"
    / "CTIO1m"
    / "defects"
    / "ccd0"
)


def _boxes(name):
    t = Table.read(_D / name, format="ascii.ecsv")
    return [(int(r["x0"]), int(r["y0"]), int(r["width"]), int(r["height"])) for r in t]


def test_base_defect_is_empty():
    # Pre-2010 base masks nothing: 2006 NGC2298 keeps all four amps.
    assert _boxes("19700101T000000.ecsv") == []


def test_2010_defect_masks_a01_quadrant():
    # A01 = lower-right quadrant of the 4064x4064 assembled detector.
    assert (2032, 0, 2032, 2032) in _boxes("20100101T000000.ecsv")


def test_2010_defect_is_only_a01():
    # The 2010 mask is exactly the dead amp -- nothing else.
    assert _boxes("20100101T000000.ecsv") == [(2032, 0, 2032, 2032)]
