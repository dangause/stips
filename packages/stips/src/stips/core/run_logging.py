"""Unified run-logging helpers for the pipeline orchestrator.

Extracted from ``stips.core.run`` to keep the orchestrator focused on step
dispatch. These set up the per-run log directory, hand out per-step log file
paths (via the ``RUN_LOG_DIR`` env var, which is also how child shell scripts
find the directory), and split interleaved LSST ``--long-log`` output into
per-exposure files for easier reading. They share no Python module state — only
the ``RUN_LOG_DIR``/``RUN_ID`` environment variables.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)


def generate_run_id() -> str:
    """Generate a unique run ID for unified logging across Python and shell."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{os.getpid()}"


def get_step_log_file(step: str, night: str = "", band: str = "") -> Path | None:
    """Get the log file path for a specific pipeline step.

    Uses RUN_LOG_DIR environment variable set by setup_run_logging.
    Organizes logs into subdirectories by step type:
    - bootstrap/ for bootstrap logs
    - templates/ for PS1 and coadd template logs
    - calibs/ for calibration logs
    - science/ for science processing logs
    - dia/ for difference imaging logs
    - fphot/ for forced photometry logs
    - lightcurve/ for lightcurve extraction logs

    Args:
        step: Pipeline step name (e.g., "bootstrap", "calibs", "science", "dia")
        night: Optional night identifier for per-night steps
        band: Optional band identifier for per-band steps

    Returns:
        Path to log file if RUN_LOG_DIR is set, None otherwise
    """
    run_log_dir = os.environ.get("RUN_LOG_DIR")
    if not run_log_dir:
        return None

    base_dir = Path(run_log_dir)

    # Map step names to subdirectories
    # Template-related steps go into templates/{band}/
    if step in ("ps1_template", "coadd_template"):
        if band:
            step_dir = base_dir / "templates" / band
        else:
            step_dir = base_dir / "templates"
        log_name = f"{step}.log"
    # Template night processing goes into separate dirs
    elif step in ("calibs_template", "science_template"):
        base_step = step.replace("_template", "")
        step_dir = base_dir / f"{base_step}_template"
        log_name = f"{night}.log" if night else f"{step}.log"
    # Regular pipeline steps
    elif step == "bootstrap":
        step_dir = base_dir / "bootstrap"
        log_name = "bootstrap.log"
    elif step == "lightcurve":
        step_dir = base_dir / "lightcurve"
        # Support multiple lightcurve extractions (forced phot vs DIA sources)
        # The 'night' parameter is used to distinguish the type
        if night:
            log_name = f"{night}.log"  # e.g., "forced_phot.log" or "dia_sources.log"
        else:
            log_name = "lightcurve.log"
    else:
        # calibs, science, dia, fphot
        step_dir = base_dir / step
        # Build filename from night and band
        parts = []
        if night:
            parts.append(night)
        if band:
            parts.append(band)
        log_name = "_".join(parts) + ".log" if parts else f"{step}.log"

    # Create step directory
    step_dir.mkdir(parents=True, exist_ok=True)

    return step_dir / log_name


def _parse_log_data_id(line: str) -> dict[str, str] | None:
    """Extract dataId from LSST long-log format.

    LSST --long-log format includes dataId in parentheses:
        (cpBiasIsr:{instrument: 'Nickel', detector: 0, exposure: 86008005, ...})

    Returns:
        Dictionary with task_label and dataId fields, or None if not found.
    """
    match = re.search(r"\((\w+):\{([^}]+)\}\)", line)
    if not match:
        return None

    data_id: dict[str, str] = {"task_label": match.group(1)}
    for kv in re.finditer(r"(\w+):\s*('([^']*)'|(\d+)|(\w+))", match.group(2)):
        data_id[kv.group(1)] = kv.group(3) or kv.group(4) or kv.group(5)
    return data_id


def split_step_logs(run_log_dir: Path) -> None:
    """Split interleaved step log files by exposure for easier reading.

    After a pipeline run, walks all step log directories and splits any log
    file with multiple exposures into per-exposure files within a subdirectory.

    For example:
        calibs/20230519.log  →  calibs/20230519/
                                  _general.log        (ingest, defineVisits, qgraph, etc.)
                                  exp85950225.log     (all tasks for this exposure)
                                  exp85950236.log
                                  exp86203012.log
    """
    step_dirs = [
        "calibs",
        "science",
        "dia",
        "fphot",
        "calibs_template",
        "science_template",
        "templates",
    ]

    for step_name in step_dirs:
        step_dir = run_log_dir / step_name
        if not step_dir.is_dir():
            continue

        for log_file in step_dir.glob("*.log"):
            _split_single_log(log_file)


def _split_single_log(log_file: Path) -> None:
    """Split a single log file by exposure/visit into a subdirectory.

    Each exposure (or visit, for DIA/fphot steps) gets one file containing
    all log lines (across all tasks) for that identifier. Lines without a
    dataId go into _general.log.
    """
    with open(log_file) as f:
        lines = f.readlines()

    grouped: dict[str, list[str]] = defaultdict(list)
    current_exposure = "_general"

    for line in lines:
        data_id = _parse_log_data_id(line)
        if data_id:
            # Calibs use "exposure", DIA/fphot use "visit"
            current_exposure = (
                data_id.get("exposure") or data_id.get("visit") or "_general"
            )
        grouped[current_exposure].append(line)

    # Only split if there are multiple exposures
    real_exposures = [k for k in grouped if k != "_general"]
    if len(real_exposures) <= 1:
        return

    split_dir = log_file.with_suffix("")
    split_dir.mkdir(parents=True, exist_ok=True)

    for exposure, exp_lines in sorted(grouped.items()):
        if exposure == "_general":
            out_path = split_dir / "_general.log"
        else:
            out_path = split_dir / f"exp{exposure}.log"
        with open(out_path, "w") as f:
            f.writelines(exp_lines)

    log.debug(
        f"Split {log_file.name} → {split_dir.name}/ "
        f"({len(real_exposures)} exposures + general)"
    )


def maybe_split_log(log_file: Path | None) -> None:
    """Split a log file by exposure if it exists and has multiple exposures."""
    if log_file and log_file.exists():
        _split_single_log(log_file)


def setup_run_logging(run_id: str, config: "Config") -> Path:
    """Set up unified logging directory for a pipeline run.

    Creates the run log directory and adds a FileHandler so all Python
    log output is captured alongside the shell script logs.

    Also sets RUN_ID in os.environ so child shell scripts (via
    run_with_stack) inherit it and write to the same directory.

    Args:
        run_id: Unique run identifier
        config: Pipeline configuration

    Returns:
        Path to the run log directory
    """
    # Use the same LOG_ROOT as logging.sh: {REPO_ROOT}/logs
    # REPO_ROOT is the monorepo root (instrument_dir.parent.parent)
    repo_root = config.instrument_dir.parent.parent
    log_root = repo_root / "logs"
    run_log_dir = log_root / run_id

    run_log_dir.mkdir(parents=True, exist_ok=True)

    # Set RUN_ID in environment so shell scripts (via run_with_stack)
    # inherit it and their logging.sh uses the same directory
    os.environ["RUN_ID"] = run_id

    # Set RUN_LOG_DIR in environment so child modules can access it
    os.environ["RUN_LOG_DIR"] = str(run_log_dir)

    # Add a file handler for Python-level logs
    pipeline_log = run_log_dir / "pipeline.log"
    file_handler = logging.FileHandler(pipeline_log)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    )

    # Add to root logger so all core modules' logs are captured
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Write run metadata
    run_info = run_log_dir / "run_info.txt"
    with open(run_info, "w") as f:
        f.write(f"Run ID: {run_id}\n")
        f.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Repository: {config.repo}\n")
        f.write(f"Pipeline log: {pipeline_log}\n")
        f.write(f"Log directory: {run_log_dir}\n")

    return run_log_dir
