"""Data collection and log parsing for the pipeline dashboard.

Scans log directories, parses run_info.txt / summary.txt / pipeline.log,
and provides data models for rendering the dashboard UI.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Phase(str, Enum):
    BOOTSTRAP = "bootstrap"
    TEMPLATES = "templates"
    CALIBS = "calibs"
    SCIENCE = "science"
    DIA = "dia"
    FPHOT = "fphot"
    LIGHTCURVE = "lightcurve"
    COMPLETE = "complete"


PHASE_ORDER = list(Phase)

# Sentinel band list used when neither a run's log nor the active profile can
# supply the bands. Renders as an explicit "unknown" column in the night grid
# rather than fabricating Nickel's r/i default (F-043).
UNKNOWN_BANDS: list[str] = ["?"]


def _profile_bands() -> list[str]:
    """Bands (dedup, order-preserving) from the active instrument profile.

    Returns [] when the profile is unavailable so callers fall back to the
    explicit-unknown sentinel instead of pretending r/i. Used only as a
    fallback when a run's log lacks a ``Bands: [...]`` line.
    """
    try:
        from stips.core.config import load_active_profile

        seen: dict[str, None] = {}
        for band in load_active_profile().filters.values():
            if band:
                seen.setdefault(band, None)
        return list(seen)
    except Exception:
        return []


@dataclass
class NightStatus:
    night: str
    calibs: str = "pending"
    science: str = "pending"
    dia: dict[str, str] = field(default_factory=dict)
    fphot: dict[str, str] = field(default_factory=dict)


@dataclass
class RunInfo:
    run_id: str
    started: str = ""
    repo: str = ""
    status: RunStatus = RunStatus.RUNNING
    current_phase: Phase = Phase.BOOTSTRAP
    object_name: str = ""
    bands: list[str] = field(default_factory=list)
    nights: list[NightStatus] = field(default_factory=list)
    calibs_ok: int = 0
    calibs_total: int = 0
    science_ok: int = 0
    science_total: int = 0
    dia_ok: int = 0
    dia_total: int = 0
    fphot_ok: int = 0
    fphot_total: int = 0
    lightcurve_ok: int = 0
    lightcurve_total: int = 0
    is_bps: bool = False
    bps_site: str = ""
    slurm_jobs: list[dict[str, str]] = field(default_factory=list)
    duration: str = ""

    @property
    def status_class(self) -> str:
        return self.status.value

    @property
    def display_bands(self) -> list[str]:
        """Bands for the night grid: the run's parsed bands, else the active
        profile's filters, else the explicit-unknown sentinel.

        Never fabricates Nickel's r/i default (F-043); when neither the run log
        nor a loadable profile supplies bands, the UI shows an explicit unknown
        column rather than silently pretending r/i.
        """
        return self.bands or _profile_bands() or UNKNOWN_BANDS


class LogTailer:
    """Tracks file offset and reads only new bytes each poll."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0

    def read_new(self) -> str:
        if not self.path.exists():
            return ""
        try:
            size = self.path.stat().st_size
            if size <= self.offset:
                return ""
            with open(self.path) as f:
                f.seek(self.offset)
                data = f.read()
            self.offset = size
            return data
        except OSError:
            return ""

    def read_tail(self, n_lines: int = 200) -> str:
        if not self.path.exists():
            return ""
        try:
            with open(self.path) as f:
                lines = f.readlines()
            self.offset = self.path.stat().st_size
            return "".join(lines[-n_lines:])
        except OSError:
            return ""


def discover_runs(logs_dir: Path) -> list[RunInfo]:
    """Scan the logs directory and return RunInfo for each run."""
    if not logs_dir.is_dir():
        return []

    runs = []
    for entry in sorted(logs_dir.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        # Run IDs look like YYYYMMDD_HHMMSS_PID
        if not re.match(r"\d{8}_\d{6}_\d+", entry.name):
            continue
        info = _parse_run(entry)
        if info is not None:
            runs.append(info)
    return runs


def get_run(logs_dir: Path, run_id: str) -> RunInfo | None:
    """Get detailed RunInfo for a single run."""
    run_dir = logs_dir / run_id
    if not run_dir.is_dir():
        return None
    return _parse_run(run_dir)


def _is_completed_bootstrap(run_dir: Path, info: RunInfo) -> bool:
    """Detect a bootstrap-only run that has already finished.

    Bootstrap runs (from ``00_bootstrap_repo.sh``) create a log directory
    with ``run_info.txt`` and ``bootstrap/`` but no ``pipeline.log`` or
    ``summary.txt``.  Once the bootstrap subdirectory has log content, the
    run is complete.
    """
    bootstrap_dir = run_dir / "bootstrap"
    if not bootstrap_dir.is_dir():
        return False
    # Must have at least one log file inside bootstrap/
    has_log = any(f.suffix == ".log" for f in bootstrap_dir.iterdir())
    return has_log


def _parse_run(run_dir: Path) -> RunInfo | None:
    """Parse a single run directory into RunInfo."""
    run_id = run_dir.name
    info = RunInfo(run_id=run_id)

    # Parse run_info.txt
    run_info_path = run_dir / "run_info.txt"
    if run_info_path.exists():
        _parse_run_info(run_info_path, info)

    # Parse summary.txt (completed runs) or pipeline.log (active runs)
    summary_path = run_dir / "summary.txt"
    if summary_path.exists():
        _parse_summary(summary_path, info)
    else:
        pipeline_log = run_dir / "pipeline.log"
        if pipeline_log.exists():
            # Active pipeline run - parse pipeline.log for phase/status
            info.status = RunStatus.RUNNING
            _parse_pipeline_log(pipeline_log, info)
        elif _is_completed_bootstrap(run_dir, info):
            # Bootstrap-only run with no pipeline.log — already finished
            info.status = RunStatus.SUCCESS
            info.current_phase = Phase.COMPLETE
        else:
            info.status = RunStatus.RUNNING

    # Calculate duration
    if info.started:
        try:
            start = datetime.fromisoformat(info.started)
            # For completed runs, use summary.txt mtime as end time
            if summary_path.exists():
                end_ts = summary_path.stat().st_mtime
                end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
            else:
                end = datetime.now(timezone.utc)
            elapsed = end - start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours >= 24:
                days = hours // 24
                hours = hours % 24
                info.duration = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                info.duration = f"{hours}h {minutes}m"
            elif minutes > 0:
                info.duration = f"{minutes}m {seconds}s"
            else:
                info.duration = f"{seconds}s"
        except (ValueError, TypeError):
            pass

    # Scan per-night subdirectories for status
    _scan_night_logs(run_dir, info)

    # Check for BPS
    pipeline_log = run_dir / "pipeline.log"
    if pipeline_log.exists():
        _detect_bps(pipeline_log, info)

    return info


def _parse_run_info(path: Path, info: RunInfo) -> None:
    """Parse run_info.txt key: value lines."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                value = value.strip()
                if key == "Run ID":
                    info.run_id = value
                elif key == "Started":
                    info.started = value
                elif key == "Repository":
                    info.repo = value
    except OSError:
        pass


def _parse_summary(path: Path, info: RunInfo) -> None:
    """Parse summary.txt for completed run data."""
    try:
        with open(path) as f:
            content = f.read()
    except OSError:
        return

    # Status
    m = re.search(r"Status:\s*(.*)", content)
    if m:
        status_str = m.group(1).strip().upper()
        if "PARTIAL" in status_str:
            info.status = RunStatus.PARTIAL
        elif "SUCCESS" in status_str:
            info.status = RunStatus.SUCCESS
        else:
            info.status = RunStatus.FAILED
    info.current_phase = Phase.COMPLETE

    # Object
    m = re.search(r"Object:\s*(.*)", content)
    if m:
        info.object_name = m.group(1).strip()

    # Bands
    m = re.search(r"Bands:\s*\[([^\]]*)\]", content)
    if m:
        info.bands = [
            b.strip().strip("'\"") for b in m.group(1).split(",") if b.strip()
        ]

    # Count patterns: "Calibs OK: N/M"
    for label, attr_ok, attr_total in [
        ("Calibs", "calibs_ok", "calibs_total"),
        ("Science", "science_ok", "science_total"),
        ("DIA", "dia_ok", "dia_total"),
        ("Fphot", "fphot_ok", "fphot_total"),
    ]:
        m = re.search(rf"{label} OK:\s*(\d+)/(\d+)", content)
        if m:
            setattr(info, attr_ok, int(m.group(1)))
            setattr(info, attr_total, int(m.group(2)))

    # Failed items for night status
    failed_calibs = _parse_failed_list(content, "Failed calibs")
    failed_science = _parse_failed_list(content, "Failed science")
    failed_dia = _parse_failed_list(content, "Failed DIA")
    failed_fphot = _parse_failed_list(content, "Failed fphot")

    # Store failed lists for cross-reference in _scan_night_logs
    info._failed_calibs = failed_calibs  # type: ignore[attr-defined]
    info._failed_science = failed_science  # type: ignore[attr-defined]
    info._failed_dia = failed_dia  # type: ignore[attr-defined]
    info._failed_fphot = failed_fphot  # type: ignore[attr-defined]


def _parse_failed_list(content: str, label: str) -> list[str]:
    """Extract a failed items list like "Failed DIA: ['20230523/i', ...]"."""
    m = re.search(rf"{label}:\s*\[([^\]]*)\]", content)
    if not m:
        return []
    return [item.strip().strip("'\"") for item in m.group(1).split(",") if item.strip()]


# Phase detection patterns in pipeline.log
_PHASE_PATTERNS = [
    (Phase.BOOTSTRAP, re.compile(r"Bootstrapping repository|running bootstrap", re.I)),
    (
        Phase.TEMPLATES,
        re.compile(r"Ingesting PS1 template|Building coadd template", re.I),
    ),
    (Phase.CALIBS, re.compile(r"Running calibrations for", re.I)),
    (Phase.SCIENCE, re.compile(r"Running science for", re.I)),
    (Phase.DIA, re.compile(r"Running DIA for|Running difference imaging", re.I)),
    (Phase.FPHOT, re.compile(r"Running forced photometry for", re.I)),
    (Phase.LIGHTCURVE, re.compile(r"Extracting lightcurve|Lightcurve using", re.I)),
    (Phase.COMPLETE, re.compile(r"Pipeline (SUCCESS|PARTIAL|FAILED)", re.I)),
]


def _parse_pipeline_log(path: Path, info: RunInfo) -> None:
    """Parse pipeline.log to detect current phase and extract metadata."""
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return

    # Detect phase from last matching line
    for line in reversed(lines):
        for phase, pattern in reversed(_PHASE_PATTERNS):
            if pattern.search(line):
                info.current_phase = phase
                break
        else:
            continue
        break

    # Extract object/bands/nights from early log lines
    for line in lines[:30]:
        m = re.search(r"Pipeline run for (\S+)", line)
        if m:
            info.object_name = m.group(1)
        m = re.search(r"Bands:\s*\[([^\]]*)\]", line)
        if m:
            info.bands = [
                b.strip().strip("'\"") for b in m.group(1).split(",") if b.strip()
            ]
        m = re.search(r"Execution:\s*(\S+)\s*\(site=(\S+)\)", line)
        if m:
            if m.group(1) == "bps":
                info.is_bps = True
                info.bps_site = m.group(2)

    # Count successes/failures from log lines
    calibs_nights: set[str] = set()
    calibs_failed: set[str] = set()
    science_nights: set[str] = set()
    science_failed: set[str] = set()
    dia_pairs: set[str] = set()
    dia_failed: set[str] = set()
    fphot_nights: set[str] = set()
    fphot_failed: set[str] = set()

    for line in lines:
        m = re.search(r"Running calibrations for (\d{8})", line)
        if m:
            calibs_nights.add(m.group(1))
        m = re.search(r"Calibrations failed for (\d{8})", line)
        if m:
            calibs_failed.add(m.group(1))
        m = re.search(r"Running science for (\d{8})", line)
        if m:
            science_nights.add(m.group(1))
        m = re.search(r"Science failed for (\d{8})", line)
        if m:
            science_failed.add(m.group(1))
        m = re.search(r"Running DIA for (\d{8})/(\w)", line)
        if m:
            dia_pairs.add(f"{m.group(1)}/{m.group(2)}")
        m = re.search(r"DIA failed for (\d{8}/\w)", line)
        if m:
            dia_failed.add(m.group(1))
        m = re.search(r"Running forced photometry for (\d{8})", line)
        if m:
            fphot_nights.add(m.group(1))
        m = re.search(r"Forced phot failed for (\d{8})", line)
        if m:
            fphot_failed.add(m.group(1))

    info.calibs_total = len(calibs_nights)
    info.calibs_ok = len(calibs_nights) - len(calibs_failed)
    info.science_total = len(science_nights)
    info.science_ok = len(science_nights) - len(science_failed)
    info.dia_total = len(dia_pairs)
    info.dia_ok = len(dia_pairs) - len(dia_failed)
    info.fphot_total = len(fphot_nights)
    info.fphot_ok = len(fphot_nights) - len(fphot_failed)

    # Lightcurve: single extraction, detect from log lines
    lc_attempted = any(
        "Extracting lightcurve" in line or "Lightcurve using" in line for line in lines
    )
    lc_failed = any("Lightcurve extraction failed" in line for line in lines)
    lc_skipped = any("skipping lightcurve extraction" in line for line in lines)
    if lc_attempted or lc_skipped:
        info.lightcurve_total = 1
        info.lightcurve_ok = 0 if (lc_failed or lc_skipped) else 1


def _scan_night_logs(run_dir: Path, info: RunInfo) -> None:
    """Scan per-night log subdirectories to build NightStatus list."""
    # Collect all nights that appear in any step subdir
    night_set: set[str] = set()
    for step_dir_name in ("calibs", "science", "dia", "fphot"):
        step_dir = run_dir / step_dir_name
        if not step_dir.is_dir():
            continue
        for entry in step_dir.iterdir():
            # Log files named YYYYMMDD.log or directories named YYYYMMDD
            name = entry.stem if entry.is_file() else entry.name
            if re.match(r"^\d{8}$", name):
                night_set.add(name)

    if not night_set:
        return

    # Get failed lists from summary parse if available
    failed_calibs = set(getattr(info, "_failed_calibs", []))
    failed_science = set(getattr(info, "_failed_science", []))
    failed_dia = set(getattr(info, "_failed_dia", []))
    failed_fphot = set(getattr(info, "_failed_fphot", []))

    # Bands for the per-band DIA/fphot columns: the run's parsed bands, else the
    # active profile's filters, else the explicit-unknown sentinel — never a
    # fabricated Nickel r/i default (F-043).
    grid_bands = info.bands or _profile_bands() or UNKNOWN_BANDS

    nights_list = []
    for night in sorted(night_set):
        ns = NightStatus(night=night)

        # Calibs status
        if _has_log(run_dir / "calibs", night):
            ns.calibs = "failed" if night in failed_calibs else "success"
        elif info.current_phase == Phase.CALIBS:
            ns.calibs = "running"

        # Science status
        if _has_log(run_dir / "science", night):
            ns.science = "failed" if night in failed_science else "success"
        elif info.current_phase == Phase.SCIENCE:
            ns.science = "running"

        # DIA status per band
        run_done = info.current_phase == Phase.COMPLETE
        dia_dir = run_dir / "dia"
        if dia_dir.is_dir():
            for band in grid_bands:
                key = f"{night}/{band}"
                if _has_log(dia_dir, f"{night}_{band}"):
                    ns.dia[band] = "failed" if key in failed_dia else "success"
                elif info.current_phase == Phase.DIA:
                    ns.dia[band] = "running"
                elif run_done:
                    ns.dia[band] = "skipped"
                else:
                    ns.dia[band] = "pending"
        else:
            for band in grid_bands:
                ns.dia[band] = "skipped" if run_done else "pending"

        # Fphot status per band
        fphot_dir = run_dir / "fphot"
        if fphot_dir.is_dir():
            for band in grid_bands:
                if _has_log(fphot_dir, f"{night}_{band}"):
                    ns.fphot[band] = "failed" if night in failed_fphot else "success"
                elif info.current_phase == Phase.FPHOT:
                    ns.fphot[band] = "running"
                elif run_done:
                    ns.fphot[band] = "skipped"
                else:
                    ns.fphot[band] = "pending"
        else:
            for band in grid_bands:
                ns.fphot[band] = "skipped" if run_done else "pending"

        nights_list.append(ns)

    info.nights = nights_list


def get_night_detail(logs_dir: Path, run_id: str, night: str) -> dict:
    """Get per-exposure detail for a specific night within a run."""
    run_dir = logs_dir / run_id
    detail: dict = {
        "night": night,
        "phases": {},
    }

    for step in ("calibs", "science"):
        step_dir = run_dir / step
        night_dir = step_dir / night
        night_log = step_dir / f"{night}.log"

        exposures = []
        if night_dir.is_dir():
            for f in sorted(night_dir.iterdir()):
                if f.suffix == ".log" and f.stem != "_general":
                    text = f.read_text(errors="replace")
                    has_error = "[ERROR]" in text or "Exception" in text
                    exposures.append(
                        {
                            "id": f.stem,
                            "status": "failed" if has_error else "success",
                            "log_path": f"{step}/{night}/{f.name}",
                        }
                    )
            general = night_dir / "_general.log"
            if general.exists():
                exposures.insert(
                    0,
                    {
                        "id": "_general",
                        "status": "info",
                        "log_path": f"{step}/{night}/_general.log",
                    },
                )
        elif night_log.exists():
            exposures.append(
                {
                    "id": "full",
                    "status": "info",
                    "log_path": f"{step}/{night}.log",
                }
            )

        detail["phases"][step] = {"exposures": exposures}

    for step in ("dia", "fphot"):
        step_dir = run_dir / step
        band_logs: list[dict] = []
        if step_dir.is_dir():
            for f in sorted(step_dir.iterdir()):
                if f.name.startswith(night) and f.suffix == ".log":
                    band = f.stem.split("_")[-1] if "_" in f.stem else "?"
                    text = f.read_text(errors="replace")
                    has_error = "[ERROR]" in text or "failed" in text.lower()
                    band_logs.append(
                        {
                            "id": f.stem,
                            "band": band,
                            "status": "failed" if has_error else "success",
                            "log_path": f"{step}/{f.name}",
                        }
                    )
        detail["phases"][step] = {"exposures": band_logs}

    return detail


def get_log_tree(logs_dir: Path, run_id: str) -> list[dict]:
    """Build a directory tree of all log files for a run."""
    run_dir = logs_dir / run_id
    if not run_dir.is_dir():
        return []

    def _build_tree(directory: Path, prefix: str = "") -> list[dict]:
        items = []
        for entry in sorted(directory.iterdir()):
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir():
                children = _build_tree(entry, rel)
                if children:
                    items.append(
                        {
                            "name": entry.name,
                            "type": "dir",
                            "path": rel,
                            "children": children,
                        }
                    )
            elif entry.suffix in (".log", ".txt", ".stdout", ".stderr"):
                items.append(
                    {
                        "name": entry.name,
                        "type": "file",
                        "path": rel,
                        "size": entry.stat().st_size,
                    }
                )
        return items

    return _build_tree(run_dir)


def _has_log(step_dir: Path, name: str) -> bool:
    """Check if a log file or split directory exists for the given name."""
    if not step_dir.is_dir():
        return False
    return (step_dir / f"{name}.log").exists() or (step_dir / name).is_dir()


def _detect_bps(pipeline_log: Path, info: RunInfo) -> None:
    """Detect BPS execution from pipeline.log."""
    try:
        with open(pipeline_log) as f:
            for line in f:
                m = re.search(r"Execution:\s*(\S+)\s*\(site=(\S+)\)", line)
                if m:
                    if m.group(1) == "bps":
                        info.is_bps = True
                        info.bps_site = m.group(2)
                    return
    except OSError:
        pass


def get_slurm_jobs() -> list[dict[str, str]]:
    """Query squeue for Slurm job status. Returns empty list if unavailable."""
    import shutil
    import subprocess

    if not shutil.which("squeue"):
        return []

    try:
        result = subprocess.run(
            ["squeue", "-u", os.environ.get("USER", ""), "-o", "%i %j %T %M %N"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        jobs = []
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return []

        for line in lines[1:]:
            parts = line.split(None, 4)
            if len(parts) >= 4:
                jobs.append(
                    {
                        "job_id": parts[0],
                        "name": parts[1],
                        "state": parts[2],
                        "time": parts[3],
                        "nodes": parts[4] if len(parts) > 4 else "",
                    }
                )
        return jobs
    except (subprocess.TimeoutExpired, OSError):
        return []
