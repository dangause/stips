"""Landolt photometric validation wrapper.

Runs validate_landolt.py inside the LSST stack environment to compare
pipeline-calibrated magnitudes against published Landolt standard star values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core.stack import run_with_stack

if TYPE_CHECKING:
    from stips.core.config import Config


@dataclass
class LandoltResult:
    success: bool
    csv_path: Path | None = None
    n_measurements: int = 0
    error: str | None = None


def run(
    *,
    config: "Config",
    catalog: Path,
    output: Path,
    collection: str = "Nickel/runs/*/processCcd/*",
    list_stars: bool = False,
    log_file: Path | None = None,
) -> LandoltResult:
    """Run Landolt validation via the LSST stack.

    Args:
        config: Loaded Config (provides repo + stack_dir).
        catalog: Path to landolt_catalog.csv.
        output: Output CSV path.
        collection: Butler collection glob.
        list_stars: If True, only list matched stars without photometry.
        log_file: Optional log path.

    Returns:
        LandoltResult with status and measurement count.
    """
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    script_path = (
        Path(__file__).parent.parent / "pipeline_tools" / "validate_landolt.py"
    )

    args = [
        "python",
        str(script_path),
        "--repo",
        str(config.repo),
        "--catalog",
        str(catalog),
        "--collection",
        collection,
        "--output",
        str(output),
    ]
    if list_stars:
        args.append("--list-stars")

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)
    except Exception as exc:
        return LandoltResult(success=False, error=str(exc))

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as fh:
            if result.stdout:
                fh.write(result.stdout)
            if result.stderr:
                fh.write(result.stderr)

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return LandoltResult(success=False, error=err or "script failed")

    # Parse measurement count from "[ok] wrote N measurements" line
    n_meas = 0
    for line in (result.stderr or "").splitlines():
        if "[ok] wrote" in line:
            try:
                n_meas = int(line.split("wrote")[1].split("measurement")[0].strip())
            except (IndexError, ValueError):
                pass
            break

    return LandoltResult(
        success=output.exists(),
        csv_path=output if output.exists() else None,
        n_measurements=n_meas,
    )
