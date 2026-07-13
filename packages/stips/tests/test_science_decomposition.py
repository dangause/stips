#!/usr/bin/env python3
"""Unit tests for the science.run decomposition (F-039, F-042).

Covers the pieces extracted from the former ~690-line run():

- ``_attempt_config`` outcome classification (rc==0 with/without parseable
  quanta, partial success, total failure, raised/fatal, raised/recoverable)
- ``_AttemptOutcome.to_attempt`` processing-log field mapping
- ``_run_config_attempts`` fold semantics (fallback shadowing order,
  cumulative counting, fatal-stop, last-attempt-failed)
- ``_is_fatal_error`` known-fatal patterns (F-042)
- ``_resolve_configs_to_try`` and ``_band_expr``
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest


def _profile() -> SimpleNamespace:
    return SimpleNamespace(
        name="Nickel",
        collection_prefix="Nickel",
        skymap_name="nickelRings-v1",
        skymap_collection="skymaps/nickelRings",
        instrument_class="lsst.obs.stips.active.Instrument",
        night_to_dayobs_offset_days=1,
        isr_overrides=None,
        crosstalk=None,
    )


def _ctx(tmp_path, executor):
    from stips.core import science
    from stips.core.pipeline import CollectionNames

    cols = CollectionNames("20230519", "20230519T000000Z", prefix="Nickel")
    config = SimpleNamespace(
        repo=tmp_path,
        resolve_config=lambda name: tmp_path / name,
    )
    return science._AttemptContext(
        config=config,
        executor=executor,
        night="20230519",
        cols=cols,
        prof=_profile(),
        pipeline=tmp_path / "DRP.yaml",
        raw_run="Nickel/raw/20230519/20230519T000000Z",
        data_query="instrument='Nickel'",
        colorterms_config=tmp_path / "apply_colorterms.py",
        refcat_mode="monster",
        qg_dir=tmp_path / "qgraphs",
        jobs=2,
        log_file=None,
    )


class _FakeExecutor:
    """Scripted executor: succeed qgraph builds, return a canned run result."""

    def __init__(self, run_result=None, qgraph_exc=None, run_exc=None):
        self.run_result = run_result
        self.qgraph_exc = qgraph_exc
        self.run_exc = run_exc
        self.calls: list[list[str]] = []

    def run_pipetask(self, args, config, **kwargs):
        self.calls.append(list(args))
        if args[0] == "qgraph":
            if self.qgraph_exc is not None:
                raise self.qgraph_exc
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if self.run_exc is not None:
            raise self.run_exc
        return self.run_result


def _patch_counts(monkeypatch, counts):
    """Force the parsed quanta counts for an attempt."""
    from stips.core import pipeline, science

    monkeypatch.setattr(
        science.quanta_report, "parse_summary_file", lambda path: counts
    )
    # Regex fallback (used when the summary file is "absent") returns (0, 0).
    # quanta_report.counts() reaches it via stips.core.pipeline.parse_quanta_summary.
    monkeypatch.setattr(pipeline, "parse_quanta_summary", lambda *a, **k: (0, 0))


# ---------------------------------------------------------------------------
# _attempt_config — outcome classification
# ---------------------------------------------------------------------------


class TestAttemptConfig:
    def test_rc0_with_counts_is_full_success(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=0, stdout="ok", stderr="")
        )
        _patch_counts(monkeypatch, (5, 0))

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.full_success
        assert not outcome.raised
        assert not outcome.partial_success
        assert not outcome.total_failure
        assert outcome.quanta_ok == 5
        assert outcome.parse_failed is False
        assert outcome.run_collection.endswith("/run")

    def test_rc0_unparseable_records_parse_failure(self, tmp_path, monkeypatch, caplog):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=0, stdout="done", stderr="")
        )
        _patch_counts(monkeypatch, None)  # summary missing -> regex gives (0, 0)
        caplog.set_level(logging.WARNING, logger=science.log.name)

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.full_success
        assert outcome.quanta_ok == 0
        assert outcome.parse_failed is True
        assert any(
            "quanta_parse_failed=True" in rec.getMessage() for rec in caplog.records
        )

    def test_nonzero_rc_with_successes_is_partial(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=1, stdout="", stderr="boom")
        )
        _patch_counts(monkeypatch, (3, 2))

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.partial_success
        assert outcome.produced_outputs
        assert (outcome.quanta_ok, outcome.quanta_fail) == (3, 2)
        assert outcome.error is None

    def test_nonzero_rc_no_successes_is_total_failure(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=1, stdout="it broke", stderr="")
        )
        _patch_counts(monkeypatch, (0, 4))

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.total_failure
        assert not outcome.produced_outputs
        assert outcome.quanta_fail == 4
        assert outcome.parse_failed is False
        assert "it broke" in outcome.error

    def test_total_failure_unparseable_marks_parse_failed(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=1, stdout="", stderr="")
        )
        _patch_counts(monkeypatch, None)

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.total_failure
        assert outcome.quanta_fail == 0
        assert outcome.parse_failed is True
        assert outcome.error == "Unknown error"

    def test_recoverable_exception_is_not_fatal(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(qgraph_exc=RuntimeError("astrometry did not converge"))
        _patch_counts(monkeypatch, None)

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.raised
        assert outcome.fatal is False
        assert "astrometry" in outcome.error

    def test_refcat_missing_exception_is_fatal(self, tmp_path, monkeypatch, caplog):
        from stips.core import science

        executor = _FakeExecutor(
            qgraph_exc=RuntimeError(
                "FileNotFoundError: no astrometry_ref_cat for htm7 12345"
            )
        )
        _patch_counts(monkeypatch, None)
        caplog.set_level(logging.INFO, logger=science.log.name)

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.raised
        assert outcome.fatal is True
        assert any(
            "Refcat missing - skipping fallback (won't help)" in rec.getMessage()
            for rec in caplog.records
        )

    def test_known_fatal_pattern_exception_is_fatal(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            qgraph_exc=RuntimeError("MissingCollectionError: Nickel/calib/current")
        )
        _patch_counts(monkeypatch, None)

        outcome = science._attempt_config(
            _ctx(tmp_path, executor), 0, tmp_path / "primary.py", []
        )

        assert outcome.raised
        assert outcome.fatal is True

    def test_fallback_uses_fb_run_and_skip_existing(self, tmp_path, monkeypatch):
        from stips.core import science

        executor = _FakeExecutor(
            run_result=SimpleNamespace(returncode=0, stdout="", stderr="")
        )
        _patch_counts(monkeypatch, (2, 0))

        outcome = science._attempt_config(
            _ctx(tmp_path, executor),
            1,
            tmp_path / "fb.py",
            ["Nickel/runs/20230519/processCcd/20230519T000000Z/run"],
        )

        assert outcome.run_collection.endswith("/run_fb1")
        qgraph_args = executor.calls[0]
        i = qgraph_args.index("--skip-existing-in")
        assert (
            qgraph_args[i + 1] == "Nickel/runs/20230519/processCcd/20230519T000000Z/run"
        )
        assert "--clobber-outputs" in qgraph_args


# ---------------------------------------------------------------------------
# _AttemptOutcome.to_attempt — processing-log field mapping
# ---------------------------------------------------------------------------


class TestToAttempt:
    def _outcome(self, **kw):
        from stips.core.science import _AttemptOutcome

        return _AttemptOutcome(run_collection="X/run", **kw)

    def test_full_success(self):
        a = self._outcome(rc=0, quanta_ok=7, quanta_fail=0).to_attempt("c.py", False)
        assert (a.quanta_succeeded, a.quanta_failed) == (7, 0)
        assert a.quanta_parse_failed is False
        assert a.error is None

    def test_full_success_parse_failed(self):
        a = self._outcome(rc=0, quanta_ok=0, parse_failed=True).to_attempt(
            "c.py", False
        )
        assert a.quanta_succeeded == 0
        assert a.quanta_parse_failed is True

    def test_partial(self):
        exps = [{"exposure": 1}]
        a = self._outcome(
            rc=1, quanta_ok=3, quanta_fail=2, failed_exposures=exps
        ).to_attempt("c.py", True)
        assert (a.quanta_succeeded, a.quanta_failed) == (3, 2)
        assert a.failed_exposures == exps
        assert a.is_fallback is True
        assert a.error is None

    def test_total_failure(self):
        a = self._outcome(
            rc=1, quanta_fail=4, error="tail of output", parse_failed=False
        ).to_attempt("c.py", False)
        assert a.quanta_succeeded == 0
        assert a.quanta_failed == 4
        assert a.error == "tail of output"
        assert a.quanta_parse_failed is False

    def test_raised_leaves_failed_count_at_zero(self):
        a = self._outcome(error="ValueError: nope").to_attempt("c.py", False)
        assert a.quanta_succeeded == 0
        assert a.quanta_failed == 0  # unknown, not fabricated
        assert a.quanta_parse_failed is True
        assert a.error == "ValueError: nope"


# ---------------------------------------------------------------------------
# _run_config_attempts — the fold
# ---------------------------------------------------------------------------


def _fold(tmp_path, monkeypatch, outcomes, configs, use_fallbacks=True):
    """Run the fold with _attempt_config stubbed to scripted outcomes."""
    from stips.core import processing_log, science

    scripted = list(outcomes)

    def fake_attempt(ctx, index, tuned_config, prior_runs):
        return scripted[index]

    monkeypatch.setattr(science, "_attempt_config", fake_attempt)
    plog = processing_log.create_log("20230519", "science")
    ctx = _ctx(tmp_path, _FakeExecutor())
    summary = science._run_config_attempts(ctx, configs, use_fallbacks, plog)
    return summary, plog


def _ok(run, n):
    from stips.core.science import _AttemptOutcome

    return _AttemptOutcome(run_collection=run, rc=0, quanta_ok=n)


def _partial(run, ok, fail):
    from stips.core.science import _AttemptOutcome

    return _AttemptOutcome(run_collection=run, rc=1, quanta_ok=ok, quanta_fail=fail)


def _dead(run, fail=3):
    from stips.core.science import _AttemptOutcome

    return _AttemptOutcome(run_collection=run, rc=1, quanta_fail=fail, error="dead")


def _raise_out(run, fatal):
    from stips.core.science import _AttemptOutcome

    return _AttemptOutcome(run_collection=run, error="boom", fatal=fatal)


class TestRunConfigAttempts:
    def _configs(self, tmp_path, n=2):
        paths = []
        for i in range(n):
            p = tmp_path / f"cfg{i}.py"
            p.write_text("# cfg\n")
            paths.append(p)
        return paths

    def test_primary_full_success_stops(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path, monkeypatch, [_ok("X/run", 5), _ok("X/run_fb1", 9)], cfgs
        )
        assert summary.any_success is True
        assert summary.fallback_used is False
        assert summary.config_used == cfgs[0]
        assert summary.successful_runs == ["X/run"]
        assert summary.cumulative_succeeded == 5
        assert len(plog.configs_tried) == 1  # fallback never attempted

    def test_partial_then_fallback_full_shadows_config_used(
        self, tmp_path, monkeypatch
    ):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path,
            monkeypatch,
            [_partial("X/run", 3, 2), _ok("X/run_fb1", 2)],
            cfgs,
        )
        assert summary.any_success is True
        assert summary.fallback_used is True
        assert summary.config_used == cfgs[1]  # last producer wins
        assert summary.successful_runs == ["X/run", "X/run_fb1"]
        assert summary.cumulative_succeeded == 5  # 3 primary + 2 rescued
        assert len(plog.configs_tried) == 2

    def test_partial_on_last_config_is_accepted(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path, n=1)
        summary, plog = _fold(tmp_path, monkeypatch, [_partial("X/run", 3, 2)], cfgs)
        assert summary.any_success is True
        assert summary.cumulative_succeeded == 3
        # last_attempt_failed semantics: remaining failures come from the
        # final attempt, never summed across attempts.
        assert plog.configs_tried[-1].quanta_failed == 2

    def test_partial_not_use_fallbacks_accepts_immediately(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path,
            monkeypatch,
            [_partial("X/run", 3, 2), _ok("X/run_fb1", 2)],
            cfgs,
            use_fallbacks=False,
        )
        assert summary.successful_runs == ["X/run"]
        assert len(plog.configs_tried) == 1  # fallback never attempted

    def test_total_failure_cascades_then_fallback_rescues(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path,
            monkeypatch,
            [_dead("X/run", fail=4), _partial("X/run_fb1", 2, 2)],
            cfgs,
        )
        assert summary.any_success is True
        assert summary.fallback_used is True
        assert summary.successful_runs == ["X/run_fb1"]  # dead run excluded
        assert summary.cumulative_succeeded == 2
        assert plog.configs_tried[-1].quanta_failed == 2  # last attempt's count

    def test_all_configs_fail(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path, monkeypatch, [_dead("X/run"), _dead("X/run_fb1")], cfgs
        )
        assert summary.any_success is False
        assert summary.successful_runs == []
        assert summary.cumulative_succeeded == 0
        assert len(plog.configs_tried) == 2

    def test_fatal_exception_stops_cascade(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path,
            monkeypatch,
            [_raise_out("X/run", fatal=True), _ok("X/run_fb1", 9)],
            cfgs,
        )
        assert summary.any_success is False
        assert len(plog.configs_tried) == 1  # fallback skipped

    def test_recoverable_exception_continues_to_fallback(self, tmp_path, monkeypatch):
        cfgs = self._configs(tmp_path)
        summary, plog = _fold(
            tmp_path,
            monkeypatch,
            [_raise_out("X/run", fatal=False), _ok("X/run_fb1", 9)],
            cfgs,
        )
        assert summary.any_success is True
        assert summary.fallback_used is True
        assert summary.successful_runs == ["X/run_fb1"]
        assert len(plog.configs_tried) == 2


# ---------------------------------------------------------------------------
# _is_fatal_error — F-042 known-fatal patterns
# ---------------------------------------------------------------------------


class TestIsFatalError:
    @pytest.mark.parametrize(
        "text",
        [
            "FileNotFoundError: no shard for astrometry_ref_cat",
            "MissingCollectionError: no collection Nickel/calib/current",
            "sqlite3.OperationalError: ConflictingDefinitionError follows",
            "OSError: [Errno 13] Permission denied: '/repo'",
            "OSError: [Errno 28] No space left on device",
        ],
    )
    def test_fatal(self, text):
        from stips.core.science import _is_fatal_error

        assert _is_fatal_error(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            # The old heuristic treated anything without a "recoverable"
            # substring as fatal; these now correctly continue to fallbacks.
            "ValueError: something odd happened",
            "Command '['bash', '-c', ...]' returned non-zero exit status 1.",
            # pipetask quantum failures are never fatal for the cascade.
            "Task calibrateImage FAILED on quantum 3",
            # astrometry_ref_cat alone (no FileNotFoundError) is not the
            # refcat-missing signature.
            "astrometry_ref_cat lookup was slow",
            # FileNotFoundError for some other dataset is retryable.
            "FileNotFoundError: connection psf_model missing",
        ],
    )
    def test_not_fatal(self, text):
        from stips.core.science import _is_fatal_error

        assert _is_fatal_error(text) is False


# ---------------------------------------------------------------------------
# _resolve_configs_to_try / _band_expr
# ---------------------------------------------------------------------------


class TestResolveConfigsToTry:
    def _cfg(self, tmp_path, primary=True, fallbacks=("fb1.py", "fb2.py")):
        from stips.core.science import ScienceConfig

        p = tmp_path / "primary.py"
        if primary:
            p.write_text("# p\n")
        fbs = []
        for name in fallbacks:
            fb = tmp_path / name
            fb.write_text("# fb\n")
            fbs.append(fb)
        return ScienceConfig(
            calibrate_image=p, colorterms=None, calibrate_image_fallbacks=fbs
        )

    def test_primary_then_fallbacks(self, tmp_path):
        from stips.core.science import _resolve_configs_to_try

        cfg = self._cfg(tmp_path)
        result = _resolve_configs_to_try(cfg, use_fallbacks=True)
        assert [p.name for p in result] == ["primary.py", "fb1.py", "fb2.py"]

    def test_no_fallbacks_when_disabled(self, tmp_path):
        from stips.core.science import _resolve_configs_to_try

        cfg = self._cfg(tmp_path)
        result = _resolve_configs_to_try(cfg, use_fallbacks=False)
        assert [p.name for p in result] == ["primary.py"]

    def test_missing_primary_dropped(self, tmp_path):
        from stips.core.science import _resolve_configs_to_try

        cfg = self._cfg(tmp_path, primary=False)
        result = _resolve_configs_to_try(cfg, use_fallbacks=True)
        assert [p.name for p in result] == ["fb1.py", "fb2.py"]

    def test_duplicate_fallback_deduped(self, tmp_path):
        from stips.core.science import ScienceConfig, _resolve_configs_to_try

        p = tmp_path / "primary.py"
        p.write_text("# p\n")
        cfg = ScienceConfig(calibrate_image=p, calibrate_image_fallbacks=[p])
        result = _resolve_configs_to_try(cfg, use_fallbacks=True)
        assert result == [p]

    def test_empty_when_nothing_exists(self, tmp_path):
        from stips.core.science import ScienceConfig, _resolve_configs_to_try

        cfg = ScienceConfig(
            calibrate_image=tmp_path / "nope.py",
            calibrate_image_fallbacks=[tmp_path / "also_nope.py"],
        )
        assert _resolve_configs_to_try(cfg, use_fallbacks=True) == []


class TestBandExpr:
    def test_none_and_empty(self):
        from stips.core.science import _band_expr

        assert _band_expr(None) == ""
        assert _band_expr([]) == ""
        assert _band_expr(["  ", ""]) == ""

    def test_normalizes_and_dedupes(self):
        from stips.core.science import _band_expr

        assert _band_expr([" R ", "i", "r"]) == " AND band IN ('r','i')"

    def test_invalid_band_raises(self):
        from stips.core.science import _band_expr

        with pytest.raises(ValueError, match="Invalid band value"):
            _band_expr(["r'; DROP TABLE"])


# ---------------------------------------------------------------------------
# run() end-to-end wiring (stubbed): chain order + result fields
# ---------------------------------------------------------------------------


def test_run_chains_fallback_runs_first(tmp_path, monkeypatch):
    """Fallback RUNs must precede the primary in the CHAINED parent."""
    from stips.core import processing_log, provenance, science

    profile = _profile()
    resolve = tmp_path / "resolved.py"
    resolve.write_text("# config\n")
    config = SimpleNamespace(
        repo=tmp_path,
        require_profile=lambda: profile,
        resolve_config=lambda name: resolve,
        resolve_pipeline=lambda name: tmp_path / "DRP.yaml",
    )

    primary = tmp_path / "primary.py"
    primary.write_text("# calibrateImage config\n")
    fb = tmp_path / "fallback.py"
    fb.write_text("# fallback config\n")
    science_cfg = science.ScienceConfig(
        calibrate_image=primary,
        colorterms=resolve,
        calibrate_image_fallbacks=[fb],
        refcat_mode="monster",
    )

    outcomes = {
        0: science._AttemptOutcome(
            run_collection="X/run", rc=1, quanta_ok=3, quanta_fail=2
        ),
        1: science._AttemptOutcome(run_collection="X/run_fb1", rc=0, quanta_ok=2),
    }
    monkeypatch.setattr(
        science,
        "_attempt_config",
        lambda ctx, index, tuned_config, prior_runs: outcomes[index],
    )

    # register-instrument + collection-chain now run through the hoisted
    # pipeline helpers (ensure_instrument_registered / redefine_chain), which
    # call pipeline.run_butler — patch there to capture the argv.
    from stips.core import pipeline as pipeline_mod

    butler_calls: list[list[str]] = []
    monkeypatch.setattr(
        pipeline_mod,
        "run_butler",
        lambda args, cfg, **k: butler_calls.append(list(args)),
    )
    monkeypatch.setattr(
        science.butler_query,
        "list_collections",
        lambda *a, **k: ["Nickel/raw/20230519/20230519T000000Z"],
    )
    monkeypatch.setattr(science.butler_query, "collection_exists", lambda *a, **k: True)
    monkeypatch.setattr(science, "_count_matching_exposures", lambda *a, **k: 5)
    monkeypatch.setattr(
        processing_log, "save_log", lambda plog, cfg: tmp_path / "l.json"
    )
    monkeypatch.setattr(provenance, "upsert_from_log", lambda *a, **k: None)

    result = science.run(
        "20230519",
        config,
        skip_coadds=True,
        science_cfg=science_cfg,
        use_fallbacks=True,
        executor=SimpleNamespace(run_pipetask=lambda *a, **k: None),
    )

    assert result.success is True
    assert result.fallback_used is True
    assert result.config_used == str(fb)
    assert result.quanta_succeeded == 5  # 3 primary + 2 rescued
    assert result.quanta_failed == 0  # last attempt fully succeeded

    chain = next(c for c in butler_calls if c[0] == "collection-chain")
    # Members after [cmd, repo, parent] and before --mode: fallback first.
    members = chain[3 : chain.index("--mode")]
    assert members == ["X/run_fb1", "X/run"]


class TestStockConfigDefault:
    """A fork with no instrument-tuned calibrateImage config runs on the
    pipeline default instead of failing (found by CTIO E2E testing)."""

    def test_default_tolerates_missing_tuned_configs(self, tmp_path):
        from unittest import mock

        from stips.core.science import ScienceConfig

        cfg = mock.Mock()
        cfg.resolve_config = lambda name: tmp_path / name  # nothing exists
        sc = ScienceConfig.default(cfg)
        assert sc.calibrate_image is None
        assert sc.calibrate_image_fallbacks == []

    def test_resolve_configs_stock_fallback(self, caplog):
        import logging

        from stips.core.science import ScienceConfig, _resolve_configs_to_try

        sc = ScienceConfig(
            calibrate_image=None, colorterms=None, calibrate_image_fallbacks=[]
        )
        with caplog.at_level(logging.INFO):
            out = _resolve_configs_to_try(sc, use_fallbacks=True)
        assert out == [None]
        assert any("pipeline default" in r.message for r in caplog.records)

    def test_resolve_configs_explicit_missing_still_fails(self, tmp_path):
        from stips.core.science import ScienceConfig, _resolve_configs_to_try

        sc = ScienceConfig(
            calibrate_image=tmp_path / "typo.py",
            colorterms=None,
            calibrate_image_fallbacks=[],
        )
        assert _resolve_configs_to_try(sc, use_fallbacks=True) == []
