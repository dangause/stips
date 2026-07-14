"""Contract test: the exact LSST-stack API surface STIPS depends on.

The structured-query modules (``core/butler_query``, ``core/quanta_report``,
``core/bps_report``) replaced fragile CLI-stdout parsing with in-stack Python
APIs. Those APIs are more stable than the CLI but **not** frozen — they have
moved and been renumbered across stack releases (v28 added ``query_datasets``;
v30 relocated the executors/quantum-report classes; ``WmsStates`` was
renumbered). This test pins the precise symbols, signatures, and *semantic
assumptions* our snippets bake in, so a stack upgrade that breaks any of them
fails **loudly in CI** instead of silently at runtime.

It only runs where the LSST stack is importable (i.e. inside the activated
stack — CI via ``scripts/with-stack.sh``); it skips cleanly otherwise. The
**canary** value comes from running it against a *newer* weekly than the pinned
one (see ``.github/workflows/stack-canary.yml``): deprecations and renames are
then caught before the production pin is bumped.

If this test goes red on a stack upgrade, the fix lives in exactly one place —
the corresponding snippet builder in the module named in each assertion.
"""

from __future__ import annotations

import importlib
import warnings

import pytest

# A stack contract test (convention: marked integration), and a hard no-op
# off-stack so the venv suite skips it cleanly.
pytestmark = pytest.mark.integration
pytest.importorskip("lsst.daf.butler", reason="LSST stack not set up")


def _import_no_future_warning(module: str, attr: str, who: str):
    """Import ``module.attr`` under FutureWarning-as-error; surface the offender.

    Catches the deprecation BEFORE the symbol is removed, with a message that
    names the STIPS module whose snippet must move.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        try:
            return getattr(importlib.import_module(module), attr)
        except FutureWarning as exc:  # pragma: no cover - only on a deprecating stack
            pytest.fail(
                f"{who}: the LSST API STIPS relies on emits a FutureWarning "
                f"(deprecated, removal pending) — update the snippet now: {exc}"
            )


class TestButlerQueryContract:
    """Surface used by core/butler_query.py snippets."""

    def test_butler_construction_and_query_methods(self):
        from lsst.daf.butler import Butler

        # Construction seam (core/butler_query builds Butler.from_config).
        assert hasattr(Butler, "from_config")
        # v28+ query surface the count/existence/list helpers call.
        assert hasattr(Butler, "query_datasets"), "Butler.query_datasets missing"

    def test_collections_accessor_methods(self):
        # query / query_info / get_info are used for list/types/has-datasets.
        # ButlerCollections is the type of `butler.collections`; assert the
        # methods exist on it without needing a live repo.
        from lsst.daf.butler import (
            Butler,
            ButlerCollections,  # type: ignore
        )

        for method in ("query", "query_info", "get_info"):
            assert hasattr(ButlerCollections, method), (
                f"butler.collections.{method} missing — "
                "core/butler_query snippet must be updated"
            )
        assert hasattr(Butler, "registry")  # v27 fallback path

    def test_data_coordinate_mapping_access(self):
        # dataset_data_id_values reads ``ref.dataId["htm7"]`` — the DataCoordinate
        # returned as a ref's dataId must support mapping-style item access by
        # dimension name. If this becomes attribute-only, the htm7 snippet breaks.
        from lsst.daf.butler import DataCoordinate

        assert hasattr(DataCoordinate, "__getitem__"), (
            "DataCoordinate no longer supports dataId[dimension] access — "
            "core/butler_query dataset_data_id_values snippet must be updated"
        )

    def test_missing_dataset_type_error_importable(self):
        # count snippets catch MissingDatasetTypeError to map to count 0.
        _import_no_future_warning(
            "lsst.daf.butler",
            "MissingDatasetTypeError",
            "butler_query (MissingDatasetTypeError)",
        )

    def test_quantum_graph_len_idiom(self):
        # Empty-qgraph check is QuantumGraph.loadUri(...) + len(qg) == 0.
        QuantumGraph = _import_no_future_warning(
            "lsst.pipe.base", "QuantumGraph", "butler_query (QuantumGraph)"
        )
        assert hasattr(QuantumGraph, "loadUri")
        assert "__len__" in dir(QuantumGraph)  # len(qg) is the documented count


class TestQuantaReportContract:
    """Semantic assumptions of core/quanta_report (parses --summary JSON)."""

    def test_execution_status_values_are_lowercase(self):
        # quanta_report keys off lowercase status strings: success / failure /
        # timeout. If the enum's serialized values change, the parser silently
        # miscounts — pin them here. Location moved ctrl_mpexec -> pipe_base at
        # ~w_2025_31, so try both (mirrors the deployment reality).
        ExecutionStatus = None
        for modname in (
            "lsst.pipe.base.quantum_reports",
            "lsst.ctrl.mpexec",
        ):
            try:
                mod = __import__(modname, fromlist=["ExecutionStatus"])
                ExecutionStatus = mod.ExecutionStatus
                break
            except (ImportError, AttributeError):
                continue
        assert ExecutionStatus is not None, (
            "ExecutionStatus not found in lsst.pipe.base.quantum_reports nor "
            "lsst.ctrl.mpexec — quanta_report's --summary assumption is broken"
        )
        values = {m.name: m.value for m in ExecutionStatus}
        assert values.get("SUCCESS") == "success", values
        assert values.get("FAILURE") == "failure", values
        # quanta_report counts TIMEOUT as a failure; confirm it still exists.
        assert "TIMEOUT" in values, values

    def test_pipetask_summary_option_exists(self):
        # quanta_report.summary_run_args adds `--summary` to the pipetask run
        # argv; confirm pipetask still accepts it (the option, not a full run).
        import subprocess

        out = subprocess.run(
            ["pipetask", "run", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert "--summary" in (out.stdout + out.stderr), (
            "pipetask run no longer accepts --summary — quanta_report must fall "
            "back to the parse_quanta_summary regex"
        )


class TestBpsReportContract:
    """Surface used by core/bps_report (ctrl_bps WmsStates / retrieve_report)."""

    def test_wms_states_members(self):
        WmsStates = _import_no_future_warning(
            "lsst.ctrl.bps", "WmsStates", "bps_report (WmsStates)"
        )
        names = {m.name for m in WmsStates}
        # bps_report looks these up by identity (never by numeric value).
        for member in ("SUCCEEDED", "FAILED", "PRUNED", "RUNNING", "READY", "UNREADY"):
            assert member in names, f"WmsStates.{member} missing: {names}"

    def test_wms_run_report_fields(self):
        import dataclasses

        WmsRunReport = _import_no_future_warning(
            "lsst.ctrl.bps", "WmsRunReport", "bps_report (WmsRunReport)"
        )
        fields = {f.name for f in dataclasses.fields(WmsRunReport)}
        for field in ("state", "job_state_counts", "total_number_jobs"):
            assert field in fields, f"WmsRunReport.{field} missing: {fields}"

    def test_retrieve_report_importable(self):
        # v28+; bps_report imports it from the submodule (not top-level).
        _import_no_future_warning(
            "lsst.ctrl.bps.report", "retrieve_report", "bps_report (retrieve_report)"
        )
