"""Tests for stips.core.clean's plan/execute split (F-041).

Discovery happens exactly once in ``plan()``; ``execute()`` removes exactly the
collections captured in that plan (no re-discovery race between the preview the
user confirmed and the deletion). Also pins the removal of the dead
``runs/*/science/*`` glob family (F-017/F-040 — nothing ever creates it).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from click.testing import CliRunner
from stips import cli as cli_module
from stips.core import clean


def _config():
    profile = SimpleNamespace(collection_prefix="Nickel")
    return SimpleNamespace(
        repo=Path("/tmp/repo"),
        require_profile=lambda: profile,
    )


def _ok_proc():
    return SimpleNamespace(returncode=0, stderr="")


# ---------------------------------------------------------------------------
# Dead-glob removal (F-017/F-040)
# ---------------------------------------------------------------------------


def test_science_glob_family_is_gone():
    # Nothing ever creates <prefix>/runs/*/science/* — science outputs live
    # under processCcd/ (and coadd outputs under coadd/).
    assert not any("/science/" in p for p in clean.run_patterns("Nickel"))
    for patterns in clean.step_patterns("Nickel").values():
        assert not any("/science/" in p for p in patterns)


# ---------------------------------------------------------------------------
# plan()
# ---------------------------------------------------------------------------


def test_plan_captures_discovery_once(monkeypatch):
    calls = []

    def fake_list(config, pattern):
        calls.append(pattern)
        return {
            "Nickel/runs/20230519/diff/ts": "CHAINED",
            "Nickel/runs/20230519/diff/ts/run": "RUN",
        }

    monkeypatch.setattr(clean.butler_query, "list_collection_types", fake_list)
    plan = clean.plan(_config())

    assert plan.error is None
    assert plan.names == [
        "Nickel/runs/20230519/diff/ts",
        "Nickel/runs/20230519/diff/ts/run",
    ]
    assert plan.collections["Nickel/runs/20230519/diff/ts/run"] == "RUN"
    # One query per pattern; no second discovery pass anywhere.
    assert calls == clean.run_patterns("Nickel")


def test_plan_filters_preserved_collections(monkeypatch):
    monkeypatch.setattr(
        clean.butler_query,
        "list_collection_types",
        lambda config, pattern: {
            "Nickel/calib/current": "CHAINED",  # always preserved
            "skymaps": "RUN",  # always preserved
            "Nickel/runs/20230519/coadd/ts/run": "RUN",
        },
    )
    plan = clean.plan(_config())
    assert plan.names == ["Nickel/runs/20230519/coadd/ts/run"]


def test_plan_rejects_unknown_step():
    plan = clean.plan(_config(), steps=["nope"])
    assert plan.error is not None
    assert "nope" in plan.error
    assert plan.is_empty


def test_plan_empty_when_nothing_found(monkeypatch):
    monkeypatch.setattr(
        clean.butler_query, "list_collection_types", lambda config, pattern: {}
    )
    plan = clean.plan(_config())
    assert plan.is_empty
    assert plan.error is None


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


def test_execute_deletes_exactly_the_plan(monkeypatch):
    # If discovery ran again inside execute(), this would blow up.
    monkeypatch.setattr(
        clean.butler_query,
        "list_collection_types",
        mock.Mock(side_effect=AssertionError("execute() must not re-discover")),
    )

    removed_cmds = []

    def fake_run_butler(args, config, **kwargs):
        removed_cmds.append(args)
        return _ok_proc()

    monkeypatch.setattr(clean, "run_butler", fake_run_butler)

    plan = clean.CleanPlan(
        collections={
            "Nickel/runs/n/diff/ts": "CHAINED",
            "Nickel/runs/n/diff/ts/run": "RUN",
            "Nickel/calib/n": "CALIBRATION",
        }
    )
    result = clean.execute(_config(), plan)

    assert result.success is True
    assert sorted(result.collections_removed) == sorted(plan.names)

    # Exactly one butler call per planned collection, with the right strategy.
    by_collection = {args[2]: args[0] for args in removed_cmds}
    assert by_collection == {
        "Nickel/runs/n/diff/ts": "remove-collections",
        "Nickel/calib/n": "remove-collections",
        "Nickel/runs/n/diff/ts/run": "remove-runs",
    }
    assert len(removed_cmds) == 3


def test_execute_empty_plan_is_noop(monkeypatch):
    run_butler = mock.Mock()
    monkeypatch.setattr(clean, "run_butler", run_butler)
    result = clean.execute(_config(), clean.CleanPlan())
    assert result.success is True
    assert result.collections_removed == []
    run_butler.assert_not_called()


def test_execute_invalid_plan_fails(monkeypatch):
    run_butler = mock.Mock()
    monkeypatch.setattr(clean, "run_butler", run_butler)
    result = clean.execute(_config(), clean.CleanPlan(error="Unknown step(s)"))
    assert result.success is False
    assert result.errors == ["Unknown step(s)"]
    run_butler.assert_not_called()


def test_execute_records_errors_and_partial_removals(monkeypatch):
    def fake_run_butler(args, config, **kwargs):
        if args[2].endswith("/run"):
            return SimpleNamespace(returncode=1, stderr="db locked")
        return _ok_proc()

    monkeypatch.setattr(clean, "run_butler", fake_run_butler)
    plan = clean.CleanPlan(
        collections={"a/chain": "CHAINED", "a/chain/run": "RUN"},
    )
    result = clean.execute(_config(), plan)
    assert result.success is False
    assert result.collections_removed == ["a/chain"]
    assert any("db locked" in e for e in result.errors)


# ---------------------------------------------------------------------------
# CLI handler: previews the plan, confirms, executes THAT plan
# ---------------------------------------------------------------------------


def test_clean_cli_executes_the_previewed_plan_object():
    plan = clean.CleanPlan(collections={"Nickel/runs/n/diff/ts/run": "RUN"})
    ok = clean.CleanResult(success=True, collections_removed=plan.names)
    with (
        mock.patch.object(cli_module, "_load_config", return_value=_config()),
        mock.patch("stips.core.clean.plan", return_value=plan) as mock_plan,
        mock.patch("stips.core.clean.execute", return_value=ok) as mock_execute,
    ):
        res = CliRunner().invoke(cli_module.cli, ["clean", "-y"])

    assert res.exit_code == 0, res.output
    mock_plan.assert_called_once()  # discovery ran exactly once
    mock_execute.assert_called_once()
    # The handler executes the very plan object it previewed.
    assert mock_execute.call_args.args[1] is plan


def test_clean_cli_dry_run_never_executes():
    plan = clean.CleanPlan(collections={"Nickel/runs/n/diff/ts/run": "RUN"})
    with (
        mock.patch.object(cli_module, "_load_config", return_value=_config()),
        mock.patch("stips.core.clean.plan", return_value=plan),
        mock.patch("stips.core.clean.execute") as mock_execute,
    ):
        res = CliRunner().invoke(cli_module.cli, ["clean", "--dry-run"])

    assert res.exit_code == 0, res.output
    assert "[DRY RUN]" in res.output
    mock_execute.assert_not_called()


def test_clean_cli_invalid_step_plan_error_exits_nonzero():
    with (
        mock.patch.object(cli_module, "_load_config", return_value=_config()),
        mock.patch(
            "stips.core.clean.plan", return_value=clean.CleanPlan(error="Unknown")
        ),
    ):
        # --step choices are click-validated; drive the plan-error path directly.
        res = CliRunner().invoke(cli_module.cli, ["clean", "-y"])
    assert res.exit_code == 1
    assert "Unknown" in res.output
