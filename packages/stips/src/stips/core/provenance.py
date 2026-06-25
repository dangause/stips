"""Aggregate per-run processing_log JSONs into a durable provenance record.

Source of truth: provenance/runs.json (list[RunRecord]).
Reference renderer: render_markdown() -> provenance/RUNS.md.
Renderers are pluggable; RUNS.md is one view of runs.json.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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
