#!/usr/bin/env python3
"""Parity + unit tests for the PipetaskStage builder and hoisted helpers (F-048).

``PipetaskStage`` collapses the qgraph-then-run pipetask choreography that was
copy-pasted across science (attempt + coadd tail), dia, calibs (bias + flat),
and coadd. These tests pin the *exact* argv each site produced BEFORE the
refactor (captured verbatim from the pre-refactor literal lists), so wiring a
site through the dataclass is provably behavior-preserving.

Also covers the ``ensure_instrument_registered`` / ``redefine_chain`` helpers and
``quanta_report.counts`` prefer-summary-else-regex block.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

sys_path_guard = str(Path(__file__).resolve().parents[1] / "src")
import sys  # noqa: E402

if sys_path_guard not in sys.path:
    sys.path.insert(0, sys_path_guard)

from stips.core import quanta_report  # noqa: E402
from stips.core.pipeline import (  # noqa: E402
    PipetaskStage,
    ensure_instrument_registered,
    redefine_chain,
)

REPO = "/repo"


# --------------------------------------------------------------------------- #
# PipetaskStage argv parity — one test per stage shape
# --------------------------------------------------------------------------- #


def test_science_attempt_primary_parity():
    """science._attempt_config primary: config-file BEFORE -d, isr AFTER -d."""
    config_file_args = [
        "--config-file",
        "calibrateImage:tuned.py",
        "--config-file",
        "calibrateImage:apply_colorterms.py",
    ]
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/x/DRP.yaml#stage1-single-visit",
        inputs="RAW,Nickel/calib/current,refcats,skymaps/x",
        output_parent="Nickel/runs/N/processCcd/ts",
        output_run="Nickel/runs/N/processCcd/ts/run",
        qgraph_path="/q/sci.qg",
        data_query="instrument='Nickel'",
        pre_query_args=config_file_args,
        post_query_args=["--config", "isr:doDefect=False"],
        jobs=8,
        run_includes_output_run=True,
        summary_file="/q/sci.summary.json",
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO,
        "-p", "/x/DRP.yaml#stage1-single-visit",
        "-i", "RAW,Nickel/calib/current,refcats,skymaps/x",
        "-o", "Nickel/runs/N/processCcd/ts",
        "--output-run", "Nickel/runs/N/processCcd/ts/run",
        "--save-qgraph", "/q/sci.qg",
        "--config-file", "calibrateImage:tuned.py",
        "--config-file", "calibrateImage:apply_colorterms.py",
        "-d", "instrument='Nickel'",
        "--config", "isr:doDefect=False",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/sci.qg",
        "--output-run", "Nickel/runs/N/processCcd/ts/run",
        "-j", "8", "--register-dataset-types",
        "--summary", "/q/sci.summary.json",
    ]  # fmt: skip


def test_science_attempt_fallback_parity():
    """Fallback attempt appends --skip-existing-in / --clobber-outputs after -d."""
    post = ["--config", "isr:doDefect=False"]
    prior = "Nickel/runs/N/processCcd/ts/run"
    post += ["--skip-existing-in", prior, "--clobber-outputs"]
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/x/DRP.yaml#stage1-single-visit",
        inputs="RAW",
        output_parent="Nickel/runs/N/processCcd/ts",
        output_run="Nickel/runs/N/processCcd/ts/run_fb1",
        qgraph_path="/q/sci_fb1.qg",
        data_query="Q",
        pre_query_args=["--config-file", "calibrateImage:fb.py"],
        post_query_args=post,
        jobs=8,
        run_includes_output_run=True,
        summary_file="/q/sci_fb1.summary.json",
    )
    qg = stage.qgraph_args()
    # Tail order preserved exactly: -d, isr override, then skip/clobber.
    assert qg[-7:] == [
        "-d", "Q",
        "--config", "isr:doDefect=False",
        "--skip-existing-in", prior,
        "--clobber-outputs",
    ]  # fmt: skip


def test_science_coadd_tail_parity():
    """science._run_coadd_tail: has -o, no run --output-run, no --summary."""
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/x/DRP.yaml#coadds-only",
        inputs="PARENT,CAL,refcats,SKY",
        output_parent="Nickel/runs/N/coadd/ts",
        output_run="Nickel/runs/N/coadd/ts/run",
        qgraph_path="/q/coadds.qg",
        data_query="instrument='Nickel' AND skymap='x'",
        jobs=6,
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO, "-p", "/x/DRP.yaml#coadds-only",
        "-i", "PARENT,CAL,refcats,SKY",
        "-o", "Nickel/runs/N/coadd/ts",
        "--output-run", "Nickel/runs/N/coadd/ts/run",
        "--save-qgraph", "/q/coadds.qg",
        "-d", "instrument='Nickel' AND skymap='x'",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/coadds.qg",
        "-j", "6", "--register-dataset-types",
    ]  # fmt: skip


def test_dia_parity():
    """dia.run: config-file AFTER -d; run has inline --output-run + --summary."""
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/p/DIA.yaml#dia-full",
        inputs="SCI,RAW,CAL,refcats,SKY,TMPL",
        output_parent="Nickel/runs/N/diff/ts",
        output_run="Nickel/runs/N/diff/ts/run",
        qgraph_path="/q/diff.qg",
        data_query="instrument='Nickel'",
        post_query_args=[
            "--config-file",
            "subtractImages:sub.py",
            "--config-file",
            "detectAndMeasureDiaSource:det.py",
        ],
        jobs=8,
        run_includes_output_run=True,
        summary_file="/q/diff.summary.json",
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO, "-p", "/p/DIA.yaml#dia-full",
        "-i", "SCI,RAW,CAL,refcats,SKY,TMPL",
        "-o", "Nickel/runs/N/diff/ts",
        "--output-run", "Nickel/runs/N/diff/ts/run",
        "--save-qgraph", "/q/diff.qg",
        "-d", "instrument='Nickel'",
        "--config-file", "subtractImages:sub.py",
        "--config-file", "detectAndMeasureDiaSource:det.py",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/diff.qg",
        "--output-run", "Nickel/runs/N/diff/ts/run",
        "-j", "8", "--register-dataset-types",
        "--summary", "/q/diff.summary.json",
    ]  # fmt: skip


def test_calibs_bias_parity():
    """calibs bias: bare pipeline path, isr after -d, plain run args."""
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/p/CpBias.yaml",
        inputs="Nickel/calib/curated,RAW",
        output_parent="Nickel/cp/N/bias",
        output_run="Nickel/cp/N/bias/ts/run",
        qgraph_path="/q/bias.qg",
        data_query="instrument='Nickel' AND exposure.observation_type='bias'",
        post_query_args=["--config", "cpBiasIsr:doDefect=False"],
        jobs=4,
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO, "-p", "/p/CpBias.yaml",
        "-i", "Nickel/calib/curated,RAW",
        "-o", "Nickel/cp/N/bias",
        "--output-run", "Nickel/cp/N/bias/ts/run",
        "--save-qgraph", "/q/bias.qg",
        "-d", "instrument='Nickel' AND exposure.observation_type='bias'",
        "--config", "cpBiasIsr:doDefect=False",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/bias.qg",
        "-j", "4", "--register-dataset-types",
    ]  # fmt: skip


def test_calibs_flat_parity():
    """calibs flat: inline -c args precede profile isr overrides, both after -d."""
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/p/CpFlat.yaml",
        inputs="CUR,RAW,CALIB,BIASRUN",
        output_parent="Nickel/cp/N/flat",
        output_run="Nickel/cp/N/flat/ts/run",
        qgraph_path="/q/flat.qg",
        data_query="instrument='Nickel' AND exposure.observation_type='flat'",
        post_query_args=[
            "-c",
            "cpFlatIsr:doDark=False",
            "-c",
            "cpFlatIsr:doOverscan=True",
            "--config",
            "cpFlatIsr:doDefect=False",
        ],
        jobs=4,
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO, "-p", "/p/CpFlat.yaml",
        "-i", "CUR,RAW,CALIB,BIASRUN",
        "-o", "Nickel/cp/N/flat",
        "--output-run", "Nickel/cp/N/flat/ts/run",
        "--save-qgraph", "/q/flat.qg",
        "-d", "instrument='Nickel' AND exposure.observation_type='flat'",
        "-c", "cpFlatIsr:doDark=False",
        "-c", "cpFlatIsr:doOverscan=True",
        "--config", "cpFlatIsr:doDefect=False",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/flat.qg",
        "-j", "4", "--register-dataset-types",
    ]  # fmt: skip


def test_coadd_parity():
    """coadd.run: NO -o (output_parent=None), config-file after -d, plain run."""
    stage = PipetaskStage(
        repo=REPO,
        pipeline="/x/DRP.yaml#coadds-only",
        inputs="IN,Nickel/calib/current,refcats,SKY",
        output_parent=None,
        output_run="templates/deep/tract100/r/ts",
        qgraph_path="/q/tmpl.qg",
        data_query="instrument='Nickel' AND skymap='x' AND tract=100 AND band='r'",
        post_query_args=["--config-file", "makeDirectWarp:mdw.py"],
        jobs=8,
    )
    assert stage.qgraph_args() == [
        "qgraph", "-b", REPO, "-p", "/x/DRP.yaml#coadds-only",
        "-i", "IN,Nickel/calib/current,refcats,SKY",
        "--output-run", "templates/deep/tract100/r/ts",
        "--save-qgraph", "/q/tmpl.qg",
        "-d", "instrument='Nickel' AND skymap='x' AND tract=100 AND band='r'",
        "--config-file", "makeDirectWarp:mdw.py",
    ]  # fmt: skip
    assert stage.run_args() == [
        "run", "-b", REPO, "-g", "/q/tmpl.qg",
        "-j", "8", "--register-dataset-types",
    ]  # fmt: skip


def test_output_parent_none_omits_dash_o():
    stage = PipetaskStage(
        repo=REPO, pipeline="P", inputs="I", output_run="R",
        qgraph_path="/q.qg", data_query="Q",
    )  # fmt: skip
    assert "-o" not in stage.qgraph_args()


# --------------------------------------------------------------------------- #
# ensure_instrument_registered
# --------------------------------------------------------------------------- #


def _config(tmp_path, instrument_class="lsst.obs.stips.active.Instrument"):
    prof = SimpleNamespace(instrument_class=instrument_class)
    return SimpleNamespace(repo=tmp_path, require_profile=lambda: prof)


def test_ensure_instrument_registered_argv(monkeypatch, tmp_path):
    from stips.core import pipeline as pipeline_mod

    calls = []
    monkeypatch.setattr(
        pipeline_mod,
        "run_butler",
        lambda args, config, **kw: calls.append((list(args), kw)),
    )
    ensure_instrument_registered(_config(tmp_path), log_file=None)

    (args, kw) = calls[0]
    assert args == [
        "register-instrument",
        str(tmp_path),
        "lsst.obs.stips.active.Instrument",
    ]
    assert kw.get("check") is False  # idempotent: tolerate already-registered


# --------------------------------------------------------------------------- #
# redefine_chain
# --------------------------------------------------------------------------- #


def test_redefine_chain_single_member(monkeypatch, tmp_path):
    from stips.core import pipeline as pipeline_mod

    calls = []
    monkeypatch.setattr(
        pipeline_mod, "run_butler", lambda args, config, **kw: calls.append(list(args))
    )
    cfg = SimpleNamespace(repo=tmp_path)
    redefine_chain(cfg, "PARENT", "RUN")
    assert calls[0] == [
        "collection-chain", str(tmp_path), "PARENT", "RUN", "--mode", "redefine",
    ]  # fmt: skip


def test_redefine_chain_member_list_preserves_order(monkeypatch, tmp_path):
    from stips.core import pipeline as pipeline_mod

    calls = []
    monkeypatch.setattr(
        pipeline_mod, "run_butler", lambda args, config, **kw: calls.append(list(args))
    )
    cfg = SimpleNamespace(repo=tmp_path)
    redefine_chain(cfg, "PARENT", ["RUN_FB1", "RUN"])
    assert calls[0] == [
        "collection-chain", str(tmp_path), "PARENT", "RUN_FB1", "RUN",
        "--mode", "redefine",
    ]  # fmt: skip


# --------------------------------------------------------------------------- #
# quanta_report.counts — prefer summary else regex fallback
# --------------------------------------------------------------------------- #


def test_counts_prefers_summary_file(tmp_path):
    summary = tmp_path / "s.json"
    quanta_report.write_summary_file(summary, 7, 3)
    assert quanta_report.counts(summary, "irrelevant output") == (7, 3)


def test_counts_falls_back_to_regex(tmp_path, monkeypatch):
    from stips.core import pipeline as pipeline_mod

    seen = {}

    def fake_regex(output, log_file, *, log_start_pos=None):
        seen["output"] = output
        seen["log_start_pos"] = log_start_pos
        return (4, 1)

    monkeypatch.setattr(pipeline_mod, "parse_quanta_summary", fake_regex)
    missing = tmp_path / "nope.json"  # parse_summary_file -> None
    result = quanta_report.counts(
        missing, "Executed 4 quanta", log_file=None, log_start_pos=99
    )
    assert result == (4, 1)
    assert seen == {"output": "Executed 4 quanta", "log_start_pos": 99}
