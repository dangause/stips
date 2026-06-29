"""Characterization tests for run.py per-night step dispatch + accounting.

These pin the observable behavior of the _run_*_step orchestrators (success
tracking, failure accounting, and the continue_on_error early-exit semantics)
so the triplication-collapse refactor can be verified without a full pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _run_cfg(**over):
    from stips.core.run import RunConfig

    base = dict(object_name="T", ra=1.0, dec=2.0, bands=["v"])
    base.update(over)
    return RunConfig(**base)


def _result():
    from stips.core.run import RunResult

    return RunResult(success=True)


def _calib(success, error=None):
    return SimpleNamespace(success=success, error=error)


class TestRunCalibsStep:
    def _call(self, nights, run_cfg, result, dry_run=False):
        from stips.core import run as runmod

        with (
            patch.object(runmod, "_get_step_log_file", return_value=None),
            patch.object(runmod, "_maybe_split_log"),
            patch("stips.core.calibs.write_curated_calibrations"),
        ):
            return runmod._run_calibs_step(
                nights, run_cfg, MagicMock(), result, dry_run, executor=MagicMock()
            )

    def test_dry_run_does_not_invoke_calibs(self):

        with patch("stips.core.calibs.run") as mrun:
            r = self._call(["20240101", "20240102"], _run_cfg(), _result(), dry_run=True)
        assert r is None
        mrun.assert_not_called()

    def test_sequential_all_succeed(self):
        res = _result()
        with patch("stips.core.calibs.run", return_value=_calib(True)) as mrun:
            r = self._call(["20240101", "20240102"], _run_cfg(), res)
        assert r is None
        assert res.failed_calibs == []
        assert mrun.call_count == 2

    def test_sequential_failure_continue_on_error(self):
        res = _result()

        def fake(night, *a, **k):
            return _calib(night != "20240101", error="boom")

        with patch("stips.core.calibs.run", side_effect=fake) as mrun:
            r = self._call(["20240101", "20240102"], _run_cfg(continue_on_error=True), res)
        assert r is None
        assert res.failed_calibs == ["20240101"]
        assert mrun.call_count == 2  # both nights run

    def test_sequential_failure_stops_when_not_continue(self):
        res = _result()
        calls = []

        def fake(night, *a, **k):
            calls.append(night)
            return _calib(False, error="boom")

        with patch("stips.core.calibs.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"], _run_cfg(continue_on_error=False), res
            )
        # early exit: returns the result, marks failure, and does NOT run night 2
        assert r is res
        assert res.success is False
        assert "20240101" in res.error
        assert calls == ["20240101"]

    def test_concurrent_all_succeed(self):
        res = _result()
        with patch("stips.core.calibs.run", return_value=_calib(True)) as mrun:
            r = self._call(
                ["20240101", "20240102"], _run_cfg(concurrent_nights=2), res
            )
        assert r is None
        assert res.failed_calibs == []
        assert mrun.call_count == 2

    def test_concurrent_failure_accounted(self):
        res = _result()

        def fake(night, *a, **k):
            return _calib(night != "20240102", error="boom")

        with patch("stips.core.calibs.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(concurrent_nights=2, continue_on_error=True),
                res,
            )
        assert r is None
        assert res.failed_calibs == ["20240102"]

    def test_concurrent_early_exit_not_continue(self):
        res = _result()

        def fake(night, *a, **k):
            return _calib(night != "20240101", error="boom")

        with patch("stips.core.calibs.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(concurrent_nights=2, continue_on_error=False),
                res,
            )
        assert r is res
        assert res.success is False


def _sci(success, fallback_used=False, config_used=None, error=None):
    return SimpleNamespace(
        success=success,
        fallback_used=fallback_used,
        config_used=config_used,
        error=error,
    )


class TestRunScienceStep:
    def _call(self, nights, run_cfg, result, dry_run=False):
        from stips.core import run as runmod

        with (
            patch.object(runmod, "_get_step_log_file", return_value=None),
            patch.object(runmod, "_maybe_split_log"),
        ):
            return runmod._run_science_step(
                nights, run_cfg, MagicMock(), result, MagicMock(), dry_run,
                executor=MagicMock(),
            )

    def test_dry_run_no_science(self):
        with patch("stips.core.science.run") as mrun:
            r = self._call(["20240101"], _run_cfg(), _result(), dry_run=True)
        assert r is None
        mrun.assert_not_called()

    def test_skips_nights_with_failed_calibs(self):
        res = _result()
        res.failed_calibs.append("20240101")
        with patch("stips.core.science.run", return_value=_sci(True)) as mrun:
            r = self._call(["20240101"], _run_cfg(), res)
        assert r is None
        assert res.failed_science == ["20240101"]
        mrun.assert_not_called()  # skipped, never run

    def test_success_single_band(self):
        res = _result()
        with patch("stips.core.science.run", return_value=_sci(True)) as mrun:
            r = self._call(["20240101"], _run_cfg(bands=["v"]), res)
        assert r is None
        assert res.failed_science == []
        assert mrun.call_count == 1

    def test_night_fails_only_when_all_band_groups_fail(self):
        # broadband group [v] + narrowband [halpha] => two groups
        res = _result()

        def fake(night, *a, bands=None, **k):
            return _sci(bands == ["v"])  # v succeeds, halpha fails

        with patch("stips.core.science.run", side_effect=fake) as mrun:
            r = self._call(["20240101"], _run_cfg(bands=["v", "halpha"]), res)
        assert r is None
        assert res.failed_science == []  # any group success => night ok
        assert mrun.call_count == 2

    def test_night_fails_when_all_groups_fail(self):
        res = _result()
        with patch("stips.core.science.run", return_value=_sci(False, error="x")):
            r = self._call(["20240101"], _run_cfg(bands=["v"]), res)
        assert r is None
        assert res.failed_science == ["20240101"]

    def test_early_exit_not_continue(self):
        res = _result()
        calls = []

        def fake(night, *a, **k):
            calls.append(night)
            return _sci(False, error="x")

        with patch("stips.core.science.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"], _run_cfg(continue_on_error=False), res
            )
        assert r is res
        assert res.success is False
        assert calls == ["20240101"]  # night 2 not started

    def test_concurrent_success(self):
        res = _result()
        with patch("stips.core.science.run", return_value=_sci(True)) as mrun:
            r = self._call(
                ["20240101", "20240102"], _run_cfg(concurrent_nights=2), res
            )
        assert r is None
        assert res.failed_science == []
        assert mrun.call_count == 2

    def test_concurrent_early_exit_not_continue(self):
        res = _result()

        def fake(night, *a, **k):
            return _sci(night != "20240101", error="x")

        with patch("stips.core.science.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(concurrent_nights=2, continue_on_error=False),
                res,
            )
        assert r is res
        assert res.success is False


def _dia(success, error=None):
    return SimpleNamespace(success=success, error=error)


class TestRunDiaStep:
    def _call(self, nights, run_cfg, result, dry_run=False, templates=("v",)):
        from stips.core import run as runmod

        for b in templates:
            result.template_collections[b] = f"templates/{b}"
        with (
            patch.object(runmod, "_get_step_log_file", return_value=None),
            patch.object(runmod, "_maybe_split_log"),
        ):
            return runmod._run_dia_step(
                nights, run_cfg, MagicMock(), result, dry_run, executor=MagicMock()
            )

    def test_skip_failed_science_marks_all_bands(self):
        res = _result()
        res.failed_science.append("20240101")
        with patch("stips.core.dia.run", return_value=_dia(True)) as mrun:
            r = self._call(["20240101"], _run_cfg(bands=["v", "r"]), res)
        assert r is None
        assert sorted(res.failed_dia) == ["20240101/r", "20240101/v"]
        mrun.assert_not_called()

    def test_missing_template_fails_band(self):
        res = _result()
        with patch("stips.core.dia.run", return_value=_dia(True)) as mrun:
            # only 'v' has a template; 'r' does not
            r = self._call(["20240101"], _run_cfg(bands=["v", "r"]), res, templates=("v",))
        assert r is None
        assert res.failed_dia == ["20240101/r"]
        assert mrun.call_count == 1  # only v ran

    def test_success(self):
        res = _result()
        with patch("stips.core.dia.run", return_value=_dia(True)):
            r = self._call(["20240101"], _run_cfg(bands=["v"]), res)
        assert r is None
        assert res.failed_dia == []

    def test_sequential_band_failure_continue(self):
        res = _result()

        def fake(night, *a, band=None, **k):
            return _dia(band != "r", error="x")

        with patch("stips.core.dia.run", side_effect=fake):
            r = self._call(["20240101"], _run_cfg(bands=["v", "r"]), res)
        assert r is None
        assert res.failed_dia == ["20240101/r"]

    def test_sequential_band_failure_early_exit(self):
        res = _result()
        calls = []

        def fake(night, *a, band=None, **k):
            calls.append((night, band))
            return _dia(False, error="x")

        with patch("stips.core.dia.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(bands=["v", "r"], continue_on_error=False),
                res,
            )
        assert r is res
        assert res.success is False
        assert calls == [("20240101", "v")]  # stops at first band failure

    def test_sequential_missing_template_does_not_early_exit(self):
        # A missing template is a graceful skip — it must NOT trigger the
        # continue_on_error abort (only a real dia.run failure does), and a
        # later band that HAS a template must still run. Regression guard.
        res = _result()
        ran = []

        def fake(night, *a, band=None, **k):
            ran.append(band)
            return _dia(True)

        with patch("stips.core.dia.run", side_effect=fake):
            # 'b' (no template) precedes 'r' (has template); not continue_on_error
            r = self._call(
                ["20240101"],
                _run_cfg(bands=["b", "r"], continue_on_error=False),
                res,
                templates=("r",),
            )
        assert r is None  # no early exit despite the missing-template band
        assert res.failed_dia == ["20240101/b"]
        assert ran == ["r"]  # the templated band still ran

    def test_concurrent_collects_failures(self):
        res = _result()

        def fake(night, *a, band=None, **k):
            return _dia(band != "r", error="x")

        with patch("stips.core.dia.run", side_effect=fake):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(bands=["v", "r"], concurrent_nights=2),
                res,
            )
        assert r is None
        assert sorted(res.failed_dia) == ["20240101/r", "20240102/r"]

    def test_concurrent_missing_template_early_exit(self):
        # Concurrent path DID and still DOES abort on a night with any failure
        # (incl. missing template) when continue_on_error is False — preserved.
        res = _result()
        with patch("stips.core.dia.run", return_value=_dia(True)):
            r = self._call(
                ["20240101"],
                _run_cfg(bands=["b"], concurrent_nights=2, continue_on_error=False),
                res,
                templates=(),  # no template for 'b'
            )
        assert r is res
        assert res.success is False


def _fp(success, colls=(), error=None):
    return SimpleNamespace(
        success=success, output_collections=list(colls), error=error
    )


class TestRunFphotStep:
    def _call(self, nights, run_cfg, result, dry_run=False):
        from stips.core import run as runmod

        with (
            patch.object(runmod, "_get_step_log_file", return_value=None),
            patch.object(runmod, "_maybe_split_log"),
        ):
            return runmod._run_fphot_step(
                nights, run_cfg, MagicMock(), result, dry_run, executor=MagicMock()
            )

    def test_skip_when_all_dia_bands_failed(self):
        res = _result()
        res.failed_dia.extend(["20240101/v"])  # only band v failed -> none left
        with patch("stips.core.fphot.run", return_value=_fp(True)) as mrun:
            r = self._call(["20240101"], _run_cfg(bands=["v"]), res)
        assert r is None
        assert res.failed_fphot == ["20240101"]
        mrun.assert_not_called()

    def test_only_runs_bands_that_passed_dia(self):
        res = _result()
        res.failed_dia.extend(["20240101/r"])  # r failed dia, v passed
        seen = []

        def fake(*a, band=None, **k):
            seen.append(band)
            return _fp(True, colls=[f"fp/{band}"])

        with patch("stips.core.fphot.run", side_effect=fake):
            r = self._call(["20240101"], _run_cfg(bands=["v", "r"]), res)
        assert r is None
        assert seen == ["v"]  # r was excluded
        assert res.forced_phot_collections == {"20240101": ["fp/v"]}
        assert res.failed_fphot == []

    def test_band_failure_records_night_and_collections(self):
        res = _result()

        def fake(*a, band=None, **k):
            return _fp(band == "v", colls=[f"fp/{band}"] if band == "v" else [])

        with patch("stips.core.fphot.run", side_effect=fake):
            r = self._call(["20240101"], _run_cfg(bands=["v", "r"]), res)
        assert r is None
        assert res.forced_phot_collections == {"20240101": ["fp/v"]}
        assert res.failed_fphot == ["20240101"]  # r failed

    def test_concurrent_records(self):
        res = _result()
        with patch("stips.core.fphot.run", return_value=_fp(True, colls=["fp/v"])):
            r = self._call(
                ["20240101", "20240102"],
                _run_cfg(bands=["v"], concurrent_nights=2),
                res,
            )
        assert r is None
        assert res.failed_fphot == []
        assert set(res.forced_phot_collections) == {"20240101", "20240102"}
