"""`stips calib-metrics --night` must select the night's UT day_obs values.

Lick observing night 20230618 is UT day_obs 20230619 (profile
night_to_dayobs_offset_days = 1), and a night can straddle UT midnight. The
extractor used to filter ``exposure.day_obs = <night>``, which matched nothing
for every Nickel night, so the paper rebuild extracted no calibration metrics
before pruning each night.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import calib_metrics  # noqa: E402


def _args_for(night, tmp_path):
    config = SimpleNamespace(
        repo=tmp_path,
        profile=SimpleNamespace(night_to_dayobs_offset_days=1),
    )
    seen = {}

    def fake_run(args, cfg, **kw):
        seen["args"] = args
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(calib_metrics, "run_with_stack", fake_run):
        calib_metrics.run(
            config=config, collection="Nickel/runs/x/processCcd/*",
            output=tmp_path / "o.csv", night=night,
        )  # fmt: skip
    return seen["args"]


def test_night_is_passed_as_its_ut_day_obs_values(tmp_path):
    args = _args_for("20230618", tmp_path)
    assert "--night" not in args
    i = args.index("--day-obs")
    assert set(args[i + 1].split(",")) == {"20230618", "20230619"}


def test_no_night_means_no_day_obs_filter(tmp_path):
    args = _args_for(None, tmp_path)
    assert "--day-obs" not in args and "--night" not in args
