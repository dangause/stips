"""Transit search must run on the differential lightcurve, not PSF photometry.

For a bright transit host (HD 189733, B = 8.6) PSF forced photometry on visit
images is unusable: the raw fluxes span a factor of four and BLS "finds" a 72%
deep transit at the edge of the period grid. The pipeline runs
DifferentialPhotTask for transit targets, but its output was never exported
and the transit search read the PSF lightcurve regardless. And when the task
found no target it still reported success.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stips.core import run as run_mod  # noqa: E402


def _result(**kw):
    return run_mod.RunResult(success=True, **kw)


def _run_cfg():
    return SimpleNamespace(
        period_min=0.5, period_max=5.0, transit_duration_min=0.5,
        transit_duration_max=4.0, period_samples=100,
        ra=300.18, dec=22.71, object_name="HD_189733", bands=["b"],
    )  # fmt: skip


def _transit_csv(result):
    fake = MagicMock()
    fake.run.return_value = SimpleNamespace(
        output_dir=Path("/tmp/x"), best_period=1.0, depth=0.02, transit_snr=10.0
    )
    with (
        patch.dict(sys.modules, {"stips.core.transit": fake}),
        patch.object(run_mod, "_get_step_log_file", return_value=None),
    ):
        import stips.core as core

        with patch.object(core, "transit", fake, create=True):
            run_mod._run_transit_step(_run_cfg(), result, dry_run=False)
    return fake.run.call_args.kwargs["csv_path"]


def test_transit_prefers_the_differential_lightcurve(tmp_path):
    result = _result(
        lightcurve_path=str(tmp_path / "psf.csv"),
        differential_lightcurve_path=str(tmp_path / "diff.csv"),
    )
    assert _transit_csv(result) == tmp_path / "diff.csv"


def test_transit_falls_back_to_the_psf_lightcurve(tmp_path):
    result = _result(lightcurve_path=str(tmp_path / "psf.csv"))
    assert _transit_csv(result) == tmp_path / "psf.csv"


def _run_diff_step(rows_exported):
    config = MagicMock()
    config.repo = Path("/repo")
    prof = MagicMock(collection_prefix="Nickel", skymap_collection="skymaps/x")
    config.require_profile.return_value = prof
    config.resolve_pipeline.return_value = Path("DifferentialPhot.yaml")
    result = _result()
    bq = MagicMock()
    bq.list_collections.return_value = ["Nickel/runs/20250802/processCcd/ts"]
    with (
        patch("stips.core.butler_query.list_collections", bq.list_collections),
        patch(
            "stips.core.stack.run_pipetask", return_value=SimpleNamespace(returncode=0)
        ),
        patch.object(run_mod, "_get_step_log_file", return_value=None),
        patch.object(
            run_mod, "_export_differential_lightcurve", return_value=rows_exported
        ),
    ):
        run_mod._run_differential_phot_step(
            ["20250802"], _run_cfg(), config, result, dry_run=False
        )
    return result


def test_differential_step_records_the_exported_lightcurve():
    result = _run_diff_step(332)
    assert result.differential_phot_success is True
    assert result.differential_lightcurve_path.endswith(
        "lightcurves/differential_HD_189733.csv"
    )


def test_empty_differential_output_is_a_failure():
    """The task finds no target (e.g. a J2000 position for a high proper-motion
    star) and writes an empty table: that must not count as success."""
    result = _run_diff_step(0)
    assert result.differential_phot_success is False
    assert result.differential_lightcurve_path is None


def test_failed_differential_skips_transit_instead_of_using_psf(tmp_path):
    """A failed differential step must not silently hand BLS the PSF
    lightcurve: for a bright host that produced a 646% 'transit' at S/N 0.9
    (v2.2.2 rebuild)."""
    result = _result(
        lightcurve_path=str(tmp_path / "psf.csv"), differential_phot_success=False
    )
    fake = MagicMock()
    with (
        patch.dict(sys.modules, {"stips.core.transit": fake}),
        patch.object(run_mod, "_get_step_log_file", return_value=None),
    ):
        run_mod._run_transit_step(_run_cfg(), result, dry_run=False)
    fake.run.assert_not_called()
    assert result.transit_result_path is None
