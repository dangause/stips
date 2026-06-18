"""Calibration metrics extraction wrapper.

Runs the `extract_calib_metrics.py` script inside the LSST stack environment
to dump per-visit astrometric/photometric calibration metrics to CSV.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core.stack import run_with_stack

if TYPE_CHECKING:
    from stips.core.config import Config


@dataclass
class CalibMetricsResult:
    success: bool
    csv_path: Path | None = None
    n_rows: int = 0
    error: str | None = None


def run(
    *,
    config: "Config",
    collection: str,
    output: Path,
    night: str | None = None,
    include_refcat_metrics: bool = False,
    log_file: Path | None = None,
) -> CalibMetricsResult:
    """Extract calibration metrics via the LSST stack.

    Args:
        config: Loaded Config (provides repo + stack_dir).
        collection: Butler collection glob (e.g. '<prefix>/runs/*/processCcd/*').
        output: Output CSV path (absolute or relative to CWD).
        night: Optional YYYYMMDD to filter by exposure.day_obs.
        include_refcat_metrics: Also pull ref-match metric bundles if present.
        log_file: Optional path for captured stdout/stderr.

    Returns:
        CalibMetricsResult with status and row count.
    """
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    script_path = (
        Path(__file__).parent.parent / "pipeline_tools" / "extract_calib_metrics.py"
    )

    args = [
        "python",
        str(script_path),
        "--repo",
        str(config.repo),
        "--collection",
        collection,
        "--output",
        str(output),
    ]
    if night:
        args.extend(["--night", str(night)])
    if include_refcat_metrics:
        args.append("--include-refcat-metrics")

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)
    except Exception as exc:
        return CalibMetricsResult(success=False, error=str(exc))

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as fh:
            if result.stdout:
                fh.write(result.stdout)
            if result.stderr:
                fh.write(result.stderr)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return CalibMetricsResult(success=False, error=err or "script failed")

    # Parse row count from the "[ok] wrote N rows ..." line on stderr.
    n_rows = 0
    for line in (result.stderr or "").splitlines():
        if "[ok] wrote" in line:
            try:
                n_rows = int(line.split("wrote")[1].split("rows")[0].strip())
            except (IndexError, ValueError):
                pass
            break

    return CalibMetricsResult(
        success=output.exists(),
        csv_path=output if output.exists() else None,
        n_rows=n_rows,
    )
