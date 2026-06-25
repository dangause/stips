"""Aggregate per-run processing_log JSONs into a durable provenance record.

Source of truth: provenance/runs.json (list[RunRecord]).
Reference renderer: render_markdown() -> provenance/RUNS.md.
Renderers are pluggable; RUNS.md is one view of runs.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
