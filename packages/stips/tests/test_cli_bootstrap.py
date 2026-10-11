"""``stips bootstrap`` CLI: unified run logging and result reporting.

A standalone ``stips bootstrap`` sets up the same ``logs/<RUN_ID>/`` directory
``stips run`` does and hands ``bootstrap.run`` the step log file
``logs/<RUN_ID>/bootstrap/bootstrap.log``. The log root is the instrument
dir's grandparent, so the tests point ``INSTRUMENT_DIR`` at a throwaway
``<tmp>/root/instruments/<name>/`` layout to keep logs out of the worktree.
"""

from __future__ import annotations

import logging
import sys
import textwrap

import pytest
from click.testing import CliRunner
from stips import cli as cli_module
from stips.core import bootstrap as bootstrap_module

_PROFILE_SRC = textwrap.dedent(
    """
    from stips import Field, InstrumentProfile, Site

    profile = InstrumentProfile(
        name="BootDemo",
        site=Site(10.0, 20.0, 100.0),
        filters={"B": "b"},
        header_map={"exposure_time": Field("EXPTIME", unit="s", default=0.0)},
        camera="camera/demo.yaml",
    )
    """
)


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    root = tmp_path / "root"
    inst = root / "instruments" / "bootdemo"
    inst.mkdir(parents=True)
    (inst / "profile.py").write_text(_PROFILE_SRC)
    repo = tmp_path / "repo"
    stack_dir = tmp_path / "stack"
    raw = tmp_path / "raw"
    for d in (stack_dir, raw):
        d.mkdir()
    f = tmp_path / "config.yaml"
    f.write_text(
        "env:\n"
        f"  REPO: {repo}\n"
        f"  STACK_DIR: {stack_dir}\n"
        f"  INSTRUMENT_DIR: {inst}\n"
        f"  RAW_PARENT_DIR: {raw}\n"
    )
    # setup_run_logging mutates os.environ and the root logger; undo both.
    monkeypatch.delenv("RUN_ID", raising=False)
    monkeypatch.delenv("RUN_LOG_DIR", raising=False)
    handlers = list(logging.getLogger().handlers)
    yield f
    for h in logging.getLogger().handlers:
        if h not in handlers:
            logging.getLogger().removeHandler(h)
            h.close()
    for name in [m for m in sys.modules if m.startswith("instruments.bootdemo")]:
        del sys.modules[name]
    while str(root) in sys.path:
        sys.path.remove(str(root))


def _invoke(cfg_file, monkeypatch, result):
    seen = {}

    def fake_run(config, **kw):
        seen.update(kw)
        return result

    monkeypatch.setattr(bootstrap_module, "run", fake_run)
    res = CliRunner().invoke(cli_module.cli, ["-c", str(cfg_file), "bootstrap"])
    return res, seen


def test_bootstrap_writes_step_log_under_run_log_dir(cfg_file, monkeypatch, tmp_path):
    res, seen = _invoke(
        cfg_file, monkeypatch, bootstrap_module.BootstrapResult(True, None)
    )
    assert res.exit_code == 0, res.output
    assert "Bootstrap complete" in res.output
    log_file = seen["log_file"]
    logs_root = tmp_path / "root" / "logs"
    assert log_file.name == "bootstrap.log"
    assert log_file.parent.name == "bootstrap"
    assert log_file.parent.parent.parent == logs_root
    assert str(log_file.parent.parent) in res.output  # "Logs: <run dir>"


def test_bootstrap_failure_exits_nonzero_with_error(cfg_file, monkeypatch):
    res, _ = _invoke(
        cfg_file,
        monkeypatch,
        bootstrap_module.BootstrapResult(
            False, "No MONSTER refcat shards found under X"
        ),
    )
    assert res.exit_code != 0
    assert "No MONSTER refcat shards found under X" in res.output


@pytest.mark.parametrize(
    "ok, status",
    [(True, "SUCCESS"), (False, "FAILED")],
)
def test_bootstrap_run_reads_as_finished_on_the_dashboard(
    cfg_file, monkeypatch, tmp_path, ok, status
):
    # setup_run_logging writes pipeline.log, which the dashboard reads as an
    # active run unless a summary.txt records the outcome.
    from stips.dashboard.collector import RunStatus, discover_runs

    _invoke(
        cfg_file,
        monkeypatch,
        bootstrap_module.BootstrapResult(ok, None if ok else "boom"),
    )
    (run,) = discover_runs(tmp_path / "root" / "logs")
    assert run.status == getattr(RunStatus, status)
