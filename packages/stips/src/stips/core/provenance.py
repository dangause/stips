"""Aggregate per-run processing_log JSONs into a durable provenance record.

Source of truth: provenance/runs.json (list[RunRecord]).
Reference renderer: render_markdown() -> provenance/RUNS.md.
Renderers are pluggable; RUNS.md is one view of runs.json.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RunRecord:
    repo: str
    repo_path: str
    target: str
    instrument: str
    night: str
    step: str
    final_status: str
    configs_tried: list[dict] = field(default_factory=list)
    total_exposures: int = 0
    successful_exposures: int = 0
    output_collection: str | None = None
    timestamp_end: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_s: int | None = None
    duration_approx: bool = False
    stips_git_sha: str | None = None
    rerun_recipe: str | None = None
    repo_size_bytes: int | None = None
    repo_status: str = "present"  # present | deleted
    reclaimed_at: str | None = None
    notes: str | None = None

    def key(self) -> tuple[str, str, str, str | None]:
        return (self.repo, self.night, self.step, self.timestamp_end)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in fields})


def _target_from_repo(repo_name: str) -> str:
    """Strip a trailing _repo / _repoN suffix to get the target/campaign name."""
    name = repo_name
    for suffix in ("_repo",):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    # strip trailing digits left from repoN style names (pg1047_repo3 -> pg1047)
    return name.rstrip("0123456789").rstrip("_") or repo_name


def _instrument_from_path(repo: Path) -> str:
    parts = {p.lower() for p in repo.parts}
    if "data_ctio" in parts or "ctio1m" in parts:
        return "ctio1m"
    return "nickel"


def record_from_log_file(log_path: Path, repo: Path) -> RunRecord:
    data = json.loads(log_path.read_text())
    return RunRecord(
        repo=repo.name,
        repo_path=str(repo),
        target=_target_from_repo(repo.name),
        instrument=_instrument_from_path(repo),
        night=data["night"],
        step=data["step"],
        final_status=data.get("final_status", "unknown"),
        configs_tried=data.get("configs_tried", []),
        total_exposures=data.get("total_exposures", 0),
        successful_exposures=data.get("successful_exposures", 0),
        output_collection=data.get("output_collection"),
        timestamp_end=data.get("timestamp"),
        started_at=data.get("started_at"),
        ended_at=data.get("ended_at"),
    )


_STAMP = "%Y%m%dT%H%M%SZ"


def duration_from_stamps(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        t0 = datetime.strptime(start, _STAMP)
        t1 = datetime.strptime(end, _STAMP)
    except ValueError:
        return None
    secs = int((t1 - t0).total_seconds())
    return (
        secs if secs > 0 else None
    )  # 0/negative => unknown (these pipelines never run in <1s)


def build_rerun_recipe(
    instrument: str, step: str, night: str, config: str | None, sha: str | None
) -> str:
    cfg = f" --config {config}" if config else ""
    at = f"  # stips @ {sha}" if sha else ""
    return f"stips {step} {night}{cfg}{at}  (instrument={instrument})"


def repo_size_bytes(repo: Path) -> int | None:
    try:
        out = subprocess.run(
            ["du", "-sk", str(repo)], capture_output=True, text=True, timeout=600
        )
        if out.returncode == 0:
            return int(out.stdout.split()[0]) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def git_sha_before(repo_root: Path, timestamp_end: str | None) -> str | None:
    """stips git SHA at-or-before run time; None if before first commit / on error."""
    if not timestamp_end:
        return None
    try:
        when = datetime.strptime(timestamp_end, _STAMP).replace(tzinfo=timezone.utc)
        out = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-list",
                "-1",
                f"--before={when.isoformat()}",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        sha = out.stdout.strip()
        return sha[:10] or None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
