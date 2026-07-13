"""Dashboard handler config handling (F-016).

The old handler wrapped ``_load_config`` in ``except (SystemExit, Exception)``,
swallowing the ``sys.exit(1)`` raised after a config error had already been
printed — then kept going. The fix: the dashboard uses the non-exiting
``_try_load_config`` (missing/invalid config is a soft condition there), and
``SystemExit`` is never caught.
"""

from unittest import mock

import click
from click.testing import CliRunner
from stips import cli as cli_module


def test_dashboard_without_config_exits_once_at_missing_logs_dir(tmp_path):
    # No -c and no ./logs: the handler degrades to the cwd fallback and exits
    # nonzero exactly once at the logs-dir check — no swallowed SystemExit, no
    # post-error continuation into the server startup.
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res = runner.invoke(cli_module.cli, ["dashboard", "--no-browser"])

    assert res.exit_code == 1
    assert "Logs directory not found" in res.output
    # The soft path prints no config error (nothing was fatally reported).
    assert "No config provided" not in res.output
    # And it never got as far as starting the dashboard.
    assert "Starting STIPS Dashboard" not in res.output


def test_dashboard_invalid_config_degrades_without_swallowing_systemexit(
    tmp_path, monkeypatch
):
    # A -c file that fails to load (ValueError) is a soft condition for the
    # dashboard: _try_load_config returns None, the handler falls back to the
    # cwd logs dir, and the command still exits cleanly-nonzero at the logs-dir
    # check rather than continuing past a printed fatal error.
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text("env: {}\n")
    monkeypatch.setattr(
        cli_module.cfg_module, "load", mock.Mock(side_effect=ValueError("bad env"))
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res = runner.invoke(
            cli_module.cli, ["-c", str(cfg_file), "dashboard", "--no-browser"]
        )

    assert res.exit_code == 1
    assert "Logs directory not found" in res.output
    assert "Starting STIPS Dashboard" not in res.output


def test_dashboard_never_catches_systemexit(tmp_path, monkeypatch):
    # Regression pin for F-016: if config resolution raises SystemExit (as
    # _load_config does after printing an error), the handler must NOT swallow
    # it and continue.
    monkeypatch.setattr(
        cli_module, "_try_load_config", mock.Mock(side_effect=SystemExit(1))
    )
    logs = tmp_path / "logs"
    logs.mkdir()

    res = CliRunner().invoke(
        cli_module.cli, ["dashboard", "--no-browser", "--logs-dir", str(logs)]
    )

    assert res.exit_code == 1
    # No continuation past the exit: the server startup banner never prints.
    assert "Starting STIPS Dashboard" not in res.output


def test_try_load_config_returns_none_instead_of_exiting(monkeypatch):
    ctx = click.Context(cli_module.cli, obj={"config_path": None})
    assert cli_module._try_load_config(ctx) is None

    ctx = click.Context(cli_module.cli, obj={"config_path": "whatever.yaml"})
    monkeypatch.setattr(
        cli_module.cfg_module, "load", mock.Mock(side_effect=ValueError("nope"))
    )
    assert cli_module._try_load_config(ctx) is None
