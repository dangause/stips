import importlib.util
import math
from pathlib import Path

import numpy as np

_S = importlib.util.spec_from_file_location(
    "probe", Path(__file__).resolve().parents[1] / "ctio_wcs_seed_probe.py")
probe = importlib.util.module_from_spec(_S)
_S.loader.exec_module(probe)


def _ring(center, radius_deg, n):
    """n points on a ring of given radius (deg) around center (ra,dec) deg."""
    ra0, dec0 = center
    pts = []
    for k in range(n):
        th = 2 * math.pi * k / n
        pts.append((ra0 + radius_deg * math.cos(th) / math.cos(math.radians(dec0)),
                    dec0 + radius_deg * math.sin(th)))
    return np.array(pts)


def test_align_score_perfect_when_no_offset():
    center = (102.2465, -36.0053)
    refs = _ring(center, 0.1, 24)
    s = probe.align_score(refs.copy(), refs, 0.0, 0.0, center)
    assert s["n_match"] == 24
    assert s["median_sep_arcsec"] < 0.1


def test_search_recovers_injected_rotation():
    # inject a known rotation: sources are refs rotated by -3 deg about center;
    # search must recover d_rot_deg ~ +3 to re-align.
    center = (102.2465, -36.0053)
    refs = _ring(center, 0.1, 36)
    src = probe.rotate_about(refs, -3.0, center)          # helper below
    best = probe.search_offset(src, refs, center,
                               rot_grid=np.arange(-6, 6.01, 0.5),
                               scale_grid=np.array([0.0]))
    assert abs(best["d_rot_deg"] - 3.0) < 0.6
    assert best["n_match"] >= 30


def test_search_recovers_injected_scale():
    center = (102.2465, -36.0053)
    refs = _ring(center, 0.1, 36)
    src = probe.scale_about(refs, -0.02, center)           # 2% too small
    best = probe.search_offset(src, refs, center,
                               rot_grid=np.array([0.0]),
                               scale_grid=np.arange(-0.05, 0.0501, 0.005))
    assert abs(best["d_scale"] - 0.02) < 0.006
