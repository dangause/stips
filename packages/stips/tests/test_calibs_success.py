"""Stack-free tests for calibs.run() success semantics (F-008, F-027d).

calibs.run() shells out to butler/pipetask and then queries the Butler for the
products it just tried to build. These tests mock those three seams
(``run_butler``, the injected ``executor.run_pipetask``, and the
``butler_query`` helpers) so we can assert that ``CalibsResult.success`` reflects
whether calibration products were actually produced — not merely whether a
qgraph was built.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import calibs  # noqa: E402

NIGHT = "20230519"


def _profile() -> MagicMock:
    prof = MagicMock()
    prof.collection_prefix = "Nickel"
    prof.instrument_class = "lsst.obs.nickel.Nickel"
    prof.name = "Nickel"
    prof.crosstalk = None
    prof.isr_overrides = {}
    return prof


def _config(tmp_path: Path) -> MagicMock:
    config = MagicMock()
    config.repo = tmp_path
    config.cp_pipe_dir = "/cp"
    config.resolve_pipeline.return_value = "CpBias.yaml"
    config.require_profile.return_value = _profile()
    return config


def _run_butler(returncode: int = 0, stderr: str = ""):
    """A run_butler stand-in returning a fixed CompletedProcess-like object."""
    mock = MagicMock(name="run_butler")
    mock.return_value = SimpleNamespace(returncode=returncode, stderr=stderr)
    return mock


def _executor(run_returncode: int = 0):
    """An executor whose run_pipetask returns a fixed return code."""
    ex = MagicMock(name="executor")
    ex.run_pipetask.return_value = SimpleNamespace(returncode=run_returncode)
    return ex


def _counts(mapping: dict[str, int]):
    """A butler_query.count_datasets side effect keyed on dataset type."""

    def _count(_config, dataset_type, _collections, **_kw):
        return mapping.get(dataset_type, 0)

    return _count


def _invoke(tmp_path, *, run_rc, counts, ingest_rc=0, ingest_stderr=""):
    """Run calibs.run() with all stack seams mocked; return (result, mocks)."""
    config = _config(tmp_path)
    executor = _executor(run_rc)
    run_butler = _run_butler(returncode=ingest_rc, stderr=ingest_stderr)
    bq = MagicMock(name="butler_query")
    bq.count_datasets.side_effect = _counts(counts)

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)

    with (
        patch.object(calibs, "run_butler", run_butler),
        patch.object(calibs, "butler_query", bq),
        patch.object(calibs, "get_raw_dir", return_value=raw_dir),
    ):
        result = calibs.run(NIGHT, config, jobs=1, executor=executor, skip_curated=True)
    return result, SimpleNamespace(run_butler=run_butler, executor=executor, bq=bq)


# --------------------------------------------------------------------------- #
# F-008: success must mean "products verified", not "qgraph built"
# --------------------------------------------------------------------------- #
def test_both_pipelines_fail_no_products_is_failure(tmp_path):
    # Pipelines exit non-zero AND the Butler holds no bias/flat products.
    result, _ = _invoke(tmp_path, run_rc=1, counts={"bias": 0, "flat": 0})

    assert result.success is False
    assert result.error is not None
    assert "Neither bias nor flat" in result.error


def test_zero_products_with_zero_returncode_is_failure(tmp_path):
    # Even a clean exit (rc=0) must fail when no products landed — proving the
    # decision is product-based, not return-code-based.
    result, _ = _invoke(tmp_path, run_rc=0, counts={"bias": 0, "flat": 0})

    assert result.success is False
    assert "Neither bias nor flat" in (result.error or "")


def test_nonzero_returncode_but_products_exist_is_partial_success(tmp_path):
    # Pipelines report partial failure (rc=1) yet produced products: success.
    result, mocks = _invoke(tmp_path, run_rc=1, counts={"bias": 2, "flat": 3})

    assert result.success is True
    assert result.error is None
    # Products verified -> both bias and flat get chained + certified.
    certify = [
        c
        for c in mocks.run_butler.call_args_list
        if c.args and c.args[0] and c.args[0][0] == "certify-calibrations"
    ]
    certified_types = {c.args[0][4] for c in certify}
    assert certified_types == {"bias", "flat"}


def test_only_bias_products_is_success(tmp_path):
    # Bias produced, flat empty: still a (partial) success, and only bias is
    # certified.
    result, mocks = _invoke(tmp_path, run_rc=0, counts={"bias": 1, "flat": 0})

    assert result.success is True
    certify = [
        c
        for c in mocks.run_butler.call_args_list
        if c.args and c.args[0] and c.args[0][0] == "certify-calibrations"
    ]
    certified_types = {c.args[0][4] for c in certify}
    assert certified_types == {"bias"}


# --------------------------------------------------------------------------- #
# F-027d: a failed ingest with no raws present is a real failure
# --------------------------------------------------------------------------- #
def test_ingest_failure_with_no_raws_is_failure(tmp_path):
    result, mocks = _invoke(
        tmp_path,
        run_rc=0,
        counts={"raw": 0, "bias": 5, "flat": 5},
        ingest_rc=1,
        ingest_stderr="No space left on device",
    )

    assert result.success is False
    assert "ingest-raws failed" in (result.error or "")
    assert "No space left on device" in result.error
    # We bailed before running any pipetask.
    mocks.executor.run_pipetask.assert_not_called()


def test_ingest_failure_but_raws_present_continues(tmp_path):
    # Benign "already ingested": ingest returns non-zero but raws exist, so
    # processing continues and can still succeed.
    result, mocks = _invoke(
        tmp_path,
        run_rc=0,
        counts={"raw": 12, "bias": 1, "flat": 1},
        ingest_rc=1,
        ingest_stderr="dataset already exists",
    )

    assert result.success is True
    mocks.executor.run_pipetask.assert_called()
