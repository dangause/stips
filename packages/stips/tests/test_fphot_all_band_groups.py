"""Forced photometry must read every science band group's collection.

Science runs per band group ("r,i" then "rp", then "ip"), each into its own
processCcd CHAINED parent. Forced photometry took only the newest parent, so
on 2020-2023 Nickel nights it saw the ip calexps but never the rp ones: in the
v2.2.1 paper rebuild 2023ixf had rp photometry on 2 of ~17 nights.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import fphot  # noqa: E402

PARENTS = [
    "Nickel/runs/20211030/processCcd/20261006T110000Z",  # ip (newest)
    "Nickel/runs/20211030/processCcd/20261006T100000Z",  # rp
]


def _inputs(image_type):
    config = MagicMock()
    config.repo = Path("/repo")
    config.require_profile.return_value = SimpleNamespace(
        name="Nickel", collection_prefix="Nickel", skymap_collection="skymaps/x",
        night_to_dayobs_offset_days=1,
    )  # fmt: skip
    config.profile = config.require_profile.return_value
    executor = MagicMock()
    executor.run_pipetask.return_value = SimpleNamespace(
        returncode=0, stdout="", stderr=""
    )
    seen = {}

    def fake_resolve(cfg, night, **kw):
        seen["kw"] = kw
        return PARENTS

    with (
        patch.object(fphot, "resolve_processccd_collections", fake_resolve),
        patch.object(
            fphot, "_select_diff_collection",
            return_value=("Nickel/runs/20211030/diff/ts/run", []),
        ),
    ):  # fmt: skip
        fphot.run("20211030", 56.65, 43.23, config, band="rp",
                  image_type=image_type, executor=executor)  # fmt: skip
    args = executor.run_pipetask.call_args.args[0]
    return seen["kw"], args[args.index("--input") + 1]


def test_asks_for_every_band_group():
    kw, _ = _inputs("diffim")
    assert kw.get("all_parents") is True


def test_diffim_inputs_include_every_science_parent():
    _, inputs = _inputs("diffim")
    for parent in PARENTS:
        assert parent in inputs.split(",")


def test_visit_inputs_include_every_science_parent():
    _, inputs = _inputs("visit")
    for parent in PARENTS:
        assert parent in inputs.split(",")
