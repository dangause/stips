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


def test_lock_reported_only_in_the_log_file_is_retried(monkeypatch, tmp_path, _no_sleep):
    """With --log-file, butler writes its traceback to the log, not stderr."""
    log_file = tmp_path / "night.log"
    log_file.write_text("earlier: database is locked\n")  # an old failure, ignored
    calls = []

    def run_with_stack(cmd, config, **kwargs):
        calls.append(cmd)
        first = len(calls) == 1
        with open(log_file, "a") as fh:
            fh.write(LOCKED if first else "INFO done\n")
        return SimpleNamespace(returncode=1 if first else 0, stdout="", stderr="", args=cmd)

    monkeypatch.setattr(stack, "run_with_stack", run_with_stack)
    result = stack.run_butler(["define-visits", "/repo", "Nickel"], object(), log_file=log_file)
    assert result.returncode == 0
    assert len(calls) == 2


def test_writers_take_turns(monkeypatch):
    """Two nights' registry writes never run at the same time."""
    import threading

    active = []
    overlap = []

    def run_with_stack(cmd, config, **kwargs):
        active.append(1)
        if len(active) > 1:
            overlap.append(cmd)
        threading.Event().wait(0.05)
        active.pop()
        return SimpleNamespace(returncode=0, stdout="", stderr="", args=cmd)

    monkeypatch.setattr(stack, "run_with_stack", run_with_stack)
    threads = [
        threading.Thread(target=stack.run_butler, args=(["ingest-raws", "/r"], object()))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlap == []


def test_old_lock_lines_in_the_log_do_not_trigger_a_retry(monkeypatch, tmp_path, _no_sleep):
    log_file = tmp_path / "night.log"
    log_file.write_text(LOCKED)
    fake, calls = _fake([(1, "")])
    monkeypatch.setattr(stack, "run_with_stack", fake)
    stack.run_butler(["ingest-raws", "/r"], object(), check=False, log_file=log_file)
    assert len(calls) == 1


def test_short_writes_do_not_wait_for_an_ingest(monkeypatch):
    """An ingest holds only the ingest turn; other writes go between its transactions."""
    import threading

    ingest_running = threading.Event()
    release_ingest = threading.Event()
    order = []

    def run_with_stack(cmd, config, **kwargs):
        if "ingest-raws" in cmd:
            ingest_running.set()
            release_ingest.wait(5)
        order.append(cmd[-2] if "ingest-raws" in cmd else cmd[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="", args=cmd)

    monkeypatch.setattr(stack, "run_with_stack", run_with_stack)
    ingest = threading.Thread(
        target=stack.run_butler, args=(["ingest-raws", "/r"], object())
    )
    ingest.start()
    assert ingest_running.wait(5)
    stack.run_butler(["certify-calibrations", "/r", "night"], object())
    release_ingest.set()
    ingest.join()
    assert order == ["night", "ingest-raws"]
