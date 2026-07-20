import csv
from pathlib import Path
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "ctio_matcher_sweep", Path(__file__).resolve().parents[1] / "ctio_matcher_sweep.py"
)
sweep = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(sweep)


def test_build_config_grid_cartesian():
    base = {"maxOffsetPix": 800, "minMatchedPairs": 15}
    axes = {"maxOffsetPix": [600, 800], "maxRotationDeg": [0.5, 1.0]}
    grid = sweep.build_config_grid(base, axes)
    assert len(grid) == 4
    # base keys survive, axis keys override
    assert all(g["minMatchedPairs"] == 15 for g in grid)
    assert {(g["maxOffsetPix"], g["maxRotationDeg"]) for g in grid} == {
        (600, 0.5), (600, 1.0), (800, 0.5), (800, 1.0)
    }


def test_render_config_is_runnable_python(tmp_path):
    p = sweep.render_config(
        {"maxOffsetPix": 800, "maxRotationDeg": 1.0, "minMatchedPairs": 15,
         "minFracMatchedPairs": 0.05, "numBrightStars": 300, "maxRefObjects": 10000,
         "numPatternConsensus": 3, "magLimitMin": 11.0, "magLimitMax": 18.0,
         "pixelMargin": 400, "psfThreshold": 5.0, "psfSpatialOrder": 2},
        tmp_path / "cand.py",
    )
    src = p.read_text()
    compile(src, str(p), "exec")                       # must be valid Python
    assert "config.astrometry.matcher.maxOffsetPix = 800" in src
    assert "base_CircularApertureFlux" in src          # neutral schema retained


def test_score_csv(tmp_path):
    csv_path = tmp_path / "m.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["visit", "astromOffsetMean"])
        w.writeheader()
        for v in ("0.3", "0.5", "0.4"):
            w.writerow({"visit": "1", "astromOffsetMean": v})
    s = sweep.score_csv(csv_path, attempted=4)
    assert s["n_pass"] == 3
    assert s["match_rate"] == 0.75
    assert abs(s["mean_sep"] - 0.4) < 1e-6
    assert s["max_sep"] == 0.5


def test_format_table_ranks_by_match_rate_then_mean(tmp_path):
    results = [
        {"label": "a", "match_rate": 0.9, "mean_sep": 0.6, "max_sep": 1.2},
        {"label": "b", "match_rate": 0.9, "mean_sep": 0.4, "max_sep": 1.0},
    ]
    out = sweep.format_table(results)
    assert out.index("b") < out.index("a")             # tie on rate -> lower mean first
