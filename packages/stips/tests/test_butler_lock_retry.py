"""Butler commands that find the SQLite registry locked are run again."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from stips.core import stack

LOCKED = "sqlite3.OperationalError: database is locked\n[SQL: BEGIN IMMEDIATE]\n"


def _fake(returns):
    calls = []

    def run_with_stack(cmd, config, **kwargs):
        calls.append(kwargs)
        rc, err = returns[len(calls) - 1]
        return SimpleNamespace(returncode=rc, stdout="", stderr=err, args=cmd)

    return run_with_stack, calls


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(stack.time, "sleep", slept.append)
    return slept


def test_locked_command_is_retried_until_it_succeeds(monkeypatch, _no_sleep, capsys):
    fake, calls = _fake([(1, LOCKED), (1, LOCKED), (0, "")])
    monkeypatch.setattr(stack, "run_with_stack", fake)

    result = stack.run_butler(["define-visits", "/repo", "Nickel"], object())

    assert result.returncode == 0
    assert len(calls) == 3
    assert _no_sleep == list(stack.LOCK_RETRY_DELAYS[:2])
    # stderr is still shown, and stdout is left alone.
    assert "database is locked" in capsys.readouterr().err
    assert all(c["capture_stderr"] and not c["capture_output"] for c in calls)


def test_other_failures_are_not_retried(monkeypatch, _no_sleep):
    fake, calls = _fake([(1, "No space left on device\n")])
    monkeypatch.setattr(stack, "run_with_stack", fake)

    result = stack.run_butler(["ingest-raws", "/repo"], object(), check=False)

    assert result.returncode == 1
    assert len(calls) == 1
    assert _no_sleep == []


def test_gives_up_after_the_last_delay_and_honours_check(monkeypatch, _no_sleep):
    fake, calls = _fake([(1, LOCKED)] * (len(stack.LOCK_RETRY_DELAYS) + 1))
    monkeypatch.setattr(stack, "run_with_stack", fake)

    with pytest.raises(subprocess.CalledProcessError):
        stack.run_butler(["certify-calibrations", "/repo"], object())
    assert len(calls) == len(stack.LOCK_RETRY_DELAYS) + 1


def test_captured_output_is_returned_not_echoed(monkeypatch, capsys):
    fake, _ = _fake([(1, LOCKED), (0, "fine\n")])
    monkeypatch.setattr(stack, "run_with_stack", fake)

    result = stack.run_butler(["ingest-raws", "/repo"], object(), capture_output=True)

    assert result.stderr == "fine\n"
    assert capsys.readouterr().err == ""
