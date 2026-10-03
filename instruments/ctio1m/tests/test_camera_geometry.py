"""Stack-free geometry sanity for the Y4KCam camera yaml.

Guards the tiling/disjointness CLASS of amp-geometry bug: each amp's data bbox
must be disjoint from its overscan bboxes and sit within its rawBBox, and the
four rawBBoxes must tile the raw frame with no gaps or overlaps. NOTE: this does
NOT catch a data bbox that is internally consistent but points at the wrong
pixels -- the amp-A01 fault was hardware-dead silicon in the 2010 run, not a
geometry error (the yaml is correct; see docs/ctio-amp-a01-finding.md). This
test exists to catch a FUTURE geometry regression and to confirm the A01 work
did not silently alter y4kcam.yaml.
"""

from pathlib import Path

import yaml

_YAML = Path(__file__).resolve().parents[1] / "camera" / "y4kcam.yaml"


def _rect(bbox):
    (x0, y0), (xe, ye) = bbox
    return (x0, y0, x0 + xe, y0 + ye)  # (xmin, ymin, xmax, ymax), half-open


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def _within(inner, outer):
    return (
        inner[0] >= outer[0]
        and inner[1] >= outer[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def _amps():
    return yaml.safe_load(_YAML.read_text())["CCDs"]["CCD0"]["amplifiers"]


def test_four_amps_named():
    assert sorted(_amps()) == ["A00", "A01", "A02", "A03"]


def test_data_disjoint_from_overscan_and_within_rawbbox():
    for name, a in _amps().items():
        data = _rect(a["rawDataBBox"])
        sos = _rect(a["rawSerialOverscanBBox"])
        pos = _rect(a["rawParallelOverscanBBox"])
        raw = _rect(a["rawBBox"])
        assert not _overlap(data, sos), f"{name}: data overlaps serial overscan"
        assert not _overlap(data, pos), f"{name}: data overlaps parallel overscan"
        assert _within(data, raw), f"{name}: data not within rawBBox"
        assert _within(sos, raw), f"{name}: serial overscan not within rawBBox"


def test_rawbboxes_tile_the_raw_frame():
    rects = [_rect(a["rawBBox"]) for a in _amps().values()]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _overlap(rects[i], rects[j]), "rawBBoxes overlap"
    total = sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)
    assert total == 4104 * 4104, f"rawBBoxes do not tile 4104x4104 (area={total})"
