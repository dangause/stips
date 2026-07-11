"""Stack-free tests for the extracted, instrument-neutral calibrateImage tuner.

Exercises the pure logic (metric scoring, failure penalization, parameter
sampling, per-trial overrides emission, dynamic CSV headers, pipetask-command
assembly, argument plumbing). optuna and the Butler/pipetask layer are not
imported here; the in-stack path is covered by a separate stack-gated one-off.
"""

import math
import tempfile
import unittest
from pathlib import Path

from stips.pipeline_tools import tune_calibrate_image as t


class _StubTrial:
    """Deterministic stand-in for an optuna Trial (no optuna dependency)."""

    def suggest_float(self, name, low, high):
        return 0.5 * (low + high)

    def suggest_int(self, name, low, high):
        return (low + high) // 2

    def suggest_categorical(self, name, choices):
        return choices[0]


class TestAggregate(unittest.TestCase):
    def test_median_odd_even(self):
        self.assertEqual(t.aggregate([3, 1, 2], "median"), 2)
        self.assertEqual(t.aggregate([1, 2, 3, 4], "median"), 2.5)

    def test_mean(self):
        self.assertEqual(t.aggregate([2, 4], "mean"), 3)

    def test_empty_is_none(self):
        self.assertIsNone(t.aggregate([], "median"))

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            t.aggregate([1, 2], "p95")


class TestScoring(unittest.TestCase):
    def test_min_and_max_direction_terms(self):
        metrics_cfg = [
            {
                "name": "psf",
                "field": "psfSigma",
                "direction": "min",
                "target": 2.0,
                "weight": 1.0,
            },
            {
                "name": "mag",
                "field": "magLim",
                "direction": "max",
                "target": 20.0,
                "weight": 1.0,
            },
        ]
        meds = {"psf": 1.0, "mag": 40.0}
        base, base2 = t.compute_metrics_and_score(meds, metrics_cfg)
        # min: 1.0*(1.0/2.0)=0.5 ; max: 1.0*(20.0/40.0)=0.5 ; total 1.0
        self.assertAlmostEqual(base, 1.0)
        self.assertEqual(base, base2)

    def test_missing_metric_is_inf(self):
        metrics_cfg = [
            {
                "name": "psf",
                "field": "f",
                "direction": "min",
                "target": 2.0,
                "weight": 1.0,
            }
        ]
        base, _ = t.compute_metrics_and_score({"psf": None}, metrics_cfg)
        self.assertTrue(math.isinf(base))

    def test_bad_direction_raises(self):
        metrics_cfg = [
            {
                "name": "x",
                "field": "f",
                "direction": "sideways",
                "target": 1.0,
                "weight": 1.0,
            }
        ]
        with self.assertRaises(ValueError):
            t.compute_metrics_and_score({"x": 1.0}, metrics_cfg)


class TestPenalize(unittest.TestCase):
    def test_hard_penalizes_any_failure(self):
        self.assertEqual(t.penalize_score(2.0, 10, 10, "hard"), 2.0)
        self.assertTrue(math.isinf(t.penalize_score(2.0, 9, 10, "hard")))

    def test_frac(self):
        self.assertAlmostEqual(t.penalize_score(2.0, 8, 10, "frac", 1.0), 2.5)

    def test_linear(self):
        self.assertAlmostEqual(t.penalize_score(2.0, 8, 10, "linear", 1.0), 6.0)

    def test_no_visits_is_inf(self):
        self.assertTrue(math.isinf(t.penalize_score(1.0, 0, 0, "frac")))


class TestSuggestParams(unittest.TestCase):
    def test_all_types(self):
        cfg = {
            "a": {"type": "float", "low": 1.0, "high": 3.0},
            "b": {"type": "int", "low": 2, "high": 6},
            "c": {"type": "categorical", "choices": ["x", "y"]},
        }
        out = t.suggest_params(_StubTrial(), cfg)
        self.assertEqual(out, {"a": 2.0, "b": 4, "c": "x"})

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            t.suggest_params(_StubTrial(), {"a": {"type": "weird"}})


class TestOverridesEmission(unittest.TestCase):
    def test_writes_apply_lines_and_prelude(self):
        param_cfg = {
            "psf_det.threshold": {
                "type": "float",
                "low": 3.0,
                "high": 8.0,
                "apply": "config.psf_detection.thresholdValue = {value}",
            }
        }
        with tempfile.TemporaryDirectory() as d:
            path = t.write_overrides_from_config(
                Path(d),
                "t000",
                {"psf_det.threshold": 5.5},
                param_cfg,
                prelude="config.foo = 1",
            )
            text = path.read_text()
            self.assertIn("# ---- Prelude ----", text)
            self.assertIn("config.foo = 1", text)
            self.assertIn("config.psf_detection.thresholdValue = 5.5", text)


class TestDynamicHeaders(unittest.TestCase):
    def _ctx(self):
        cfg = {
            "parameters": {"p1": {}, "p2": {}},
            "metrics": [{"name": "psf"}, {"name": "mag"}],
        }
        return t.Context(
            repo=Path("."),
            pipeline_dir=Path("."),
            proc_pipe=Path("x"),
            post_pipe=Path("y"),
            workdir=Path("."),
            visits=[1],
            bad=[],
            jobs=1,
            inputs_postisr="c",
            calib_chain="cc",
            refcats="refcats",
            fail_policy="frac",
            fail_weight=1.0,
            echo_logs=False,
            tail=20,
            run_postproc=False,
            cfg=cfg,
            instrument="Nickel",
            prefix="Nickel",
        )

    def test_headers_include_metrics_and_params(self):
        headers = t.make_runs_headers(self._ctx())
        self.assertIn("psf", headers)
        self.assertIn("mag", headers)
        self.assertIn("p1", headers)
        self.assertIn("p2", headers)

    def test_calibrate_cmd_uses_instrument_and_prefix(self):
        ctx = self._ctx()
        cmd = t.build_calibrate_cmd(
            ctx, Path("/ov.py"), 12345, "Nickel/run/calib_tune/t000"
        )
        joined = " ".join(cmd)
        self.assertIn("instrument='Nickel'", joined)
        self.assertIn("visit IN (12345)", joined)
        self.assertIn("calibrateImage:/ov.py", joined)


class TestArgumentPlumbing(unittest.TestCase):
    def test_required_and_defaults(self):
        args = t.build_parser().parse_args(
            ["--repo", "r", "--pipeline-dir", "p", "--workdir", "w", "--config", "c"]
        )
        self.assertEqual(args.trials, 20)
        self.assertEqual(args.fail_policy, "frac")
        self.assertIsNone(args.instrument)
        self.assertIsNone(args.collection_prefix)

    def test_missing_required_exits(self):
        with self.assertRaises(SystemExit):
            t.build_parser().parse_args(["--repo", "r"])


if __name__ == "__main__":
    unittest.main()
