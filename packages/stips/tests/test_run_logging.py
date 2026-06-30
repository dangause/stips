"""Tests for stips.core.run_logging (extracted from run.py)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_generate_run_id_format():
    from stips.core import run_logging

    rid = run_logging.generate_run_id()
    # YYYYMMDD_HHMMSS_PID
    assert re.match(r"^\d{8}_\d{6}_\d+$", rid)


def test_get_step_log_file_none_without_env(monkeypatch):
    from stips.core import run_logging

    monkeypatch.delenv("RUN_LOG_DIR", raising=False)
    assert run_logging.get_step_log_file("calibs", night="20240101") is None


def test_get_step_log_file_paths(monkeypatch, tmp_path):
    from stips.core import run_logging

    monkeypatch.setenv("RUN_LOG_DIR", str(tmp_path))
    # per-night/band steps -> <step>/<night>_<band>.log
    assert run_logging.get_step_log_file("dia", "20240101", "v") == (
        tmp_path / "dia" / "20240101_v.log"
    )
    assert run_logging.get_step_log_file("calibs", "20240101") == (
        tmp_path / "calibs" / "20240101.log"
    )
    # bootstrap is a fixed file
    assert run_logging.get_step_log_file("bootstrap") == (
        tmp_path / "bootstrap" / "bootstrap.log"
    )
    # template steps nest under templates/<band>
    assert run_logging.get_step_log_file("ps1_template", band="r") == (
        tmp_path / "templates" / "r" / "ps1_template.log"
    )


def test_split_single_log_splits_by_exposure(tmp_path):
    from stips.core import run_logging

    log_file = tmp_path / "20240101.log"
    log_file.write_text(
        "start\n"
        "(isr:{instrument: 'CTIO1m', detector: 0, exposure: 111})\n"
        "more 111\n"
        "(isr:{instrument: 'CTIO1m', detector: 0, exposure: 222})\n"
        "more 222\n"
    )
    run_logging._split_single_log(log_file)
    split_dir = tmp_path / "20240101"
    assert (split_dir / "exp111.log").exists()
    assert (split_dir / "exp222.log").exists()
    assert "more 111" in (split_dir / "exp111.log").read_text()
    assert "start" in (split_dir / "_general.log").read_text()


def test_split_single_log_noop_for_single_exposure(tmp_path):
    from stips.core import run_logging

    log_file = tmp_path / "one.log"
    log_file.write_text("(isr:{instrument: 'CTIO1m', exposure: 111})\nx\n")
    run_logging._split_single_log(log_file)
    # only one exposure -> no split directory created
    assert not (tmp_path / "one").exists()
