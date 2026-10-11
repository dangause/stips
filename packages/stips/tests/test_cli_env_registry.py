"""``stips env`` CLI: distinguish a failed registry query from an empty repo.

``stips.core.butler_query.list_instruments(config)`` returns ``None`` when the
in-stack registry query itself failed, and ``{}`` when the repo simply holds no
instruments yet. ``stips.core.pipeline.ensure_instrument_registered`` already
keeps that distinction (see ``test_pipetask_stage.py``), but the ``env`` command
collapsed both into the same "(none; run `stips bootstrap`)" message, which
tells a user with a populated-but-unreachable repo to bootstrap it instead of
pointing at the real (stack/registry) problem.

These tests pin the three outputs ``stips env`` can print for the "Registered
instruments:" section: a failed query, a genuinely empty repo, and a populated
repo (including the legacy-class annotation).
"""

from pathlib import Path

from click.testing import CliRunner
from stips import cli as cli_module
from stips.core import butler_query as butler_query_module
from stips.core import stack as stack_module

REPO_ROOT = Path(__file__).resolve().parents[3]
NICKEL_INSTRUMENT_DIR = REPO_ROOT / "instruments" / "nickel"

NEW_CLS = "instruments.nickel.instrument.Instrument"
LEGACY_CLS = "lsst.obs.stips.active.Instrument"


def _write_config(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "butler.yaml").write_text("")

    stack_dir = tmp_path / "stack"
    stack_dir.mkdir()
    raw_parent_dir = tmp_path / "raw"
    raw_parent_dir.mkdir()

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "\n".join(
            [
                "env:",
                f"  REPO: {repo}",
                f"  STACK_DIR: {stack_dir}",
                f"  INSTRUMENT_DIR: {NICKEL_INSTRUMENT_DIR}",
                f"  RAW_PARENT_DIR: {raw_parent_dir}",
            ]
        )
        + "\n"
    )
    return cfg_file


def _invoke(tmp_path, monkeypatch, registered):
    cfg_file = _write_config(tmp_path)
    monkeypatch.setattr(stack_module, "check_stack", lambda config: True)
    monkeypatch.setattr(
        butler_query_module, "list_instruments", lambda config: registered
    )

    runner = CliRunner()
    return runner.invoke(cli_module.cli, ["-c", str(cfg_file), "env"])


def test_env_reports_failed_registry_query(tmp_path, monkeypatch):
    res = _invoke(tmp_path, monkeypatch, None)

    assert res.exit_code == 0, res.output
    assert "could not query the registry; see the stack log above" in res.output
    assert "run `stips bootstrap`" not in res.output


def test_env_reports_empty_repo(tmp_path, monkeypatch):
    res = _invoke(tmp_path, monkeypatch, {})

    assert res.exit_code == 0, res.output
    assert "(none; run `stips bootstrap`)" in res.output
    assert "could not query" not in res.output


def test_env_reports_populated_repo_with_legacy_marker(tmp_path, monkeypatch):
    res = _invoke(tmp_path, monkeypatch, {"Nickel": LEGACY_CLS})

    assert res.exit_code == 0, res.output
    assert "could not query" not in res.output
    assert "run `stips bootstrap`" not in res.output
    assert "Nickel" in res.output
    assert LEGACY_CLS in res.output
    assert "legacy; migrates on the next step" in res.output
