"""Aggregate per-run processing_log JSONs into a durable provenance record.

Source of truth: provenance/runs.json (list[RunRecord]).
Reference renderer: render_markdown() -> provenance/RUNS.md.
Renderers are pluggable; RUNS.md is one view of runs.json.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_LSST_VER = re.compile(r"lsst-scipipe-[0-9][0-9A-Za-z._]*")


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
    stips_git_describe: str | None = None
    lsst_stack_version: str | None = None
    lsst_stack_version_source: str | None = None  # "repo-scan" | "env"
    # Actual LSST *pipelines* (EUPS package) version, e.g. "gf03f954c0e+3d14ea8aaf",
    # captured live from lsst.daf.butler in the activated stack. Distinct from
    # lsst_stack_version above, which records the rubin-env/conda env name
    # (lsst-scipipe-*) — a runtime identifier two releases can share. New in F-019;
    # absent (None) on records written before this field existed.
    lsst_pipelines_version: str | None = None
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
    """Best-effort instrument guess from the repo path.

    A last-resort fallback for contexts with no loaded profile (e.g. scanning
    historical log dirs via ``sync``). Prefer the active profile's name when a
    ``Config`` is available (see ``instrument_from_config``). Returns the
    explicit sentinel ``"unknown"`` rather than assuming any one instrument, so a
    fork's runs are never mislabelled as the reference profile.
    """
    parts = {p.lower() for p in repo.parts}
    if "data_ctio" in parts or "ctio1m" in parts:
        return "ctio1m"
    return "unknown"


def instrument_from_config(config) -> str | None:
    """Instrument name from the active profile (lowercased), or None.

    The authoritative source when a ``Config`` is in hand: it reflects the
    profile actually selected via ``INSTRUMENT_DIR``, not a path heuristic.
    """
    profile = getattr(config, "profile", None)
    name = getattr(profile, "name", None)
    return name.lower() if isinstance(name, str) and name else None


def record_from_log_file(
    log_path: Path, repo: Path, instrument: str | None = None
) -> RunRecord:
    data = json.loads(log_path.read_text())
    return RunRecord(
        repo=repo.name,
        repo_path=str(repo),
        target=_target_from_repo(repo.name),
        instrument=instrument or _instrument_from_path(repo),
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


def lsst_version_from_repo(repo: Path) -> str | None:
    """Best-effort: grep the repo tree for the lsst-scipipe env marker."""
    try:
        out = subprocess.run(
            ["grep", "-rahom1", "lsst-scipipe-[0-9][0-9.]*", str(repo)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        m = _LSST_VER.search(out.stdout or "")
        return m.group(0) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def lsst_version_from_env() -> str | None:
    """Live capture: detect the active lsst-scipipe conda env."""
    import sys

    for val in (
        os.environ.get("CONDA_DEFAULT_ENV", ""),
        os.environ.get("CONDA_PREFIX", ""),
        sys.prefix,
    ):
        m = _LSST_VER.search(val or "")
        if m:
            return m.group(0)
    return None


def git_describe(repo_root: Path, sha: str | None) -> str | None:
    if not sha:
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "describe", "--tags", "--always", sha],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_rerun_recipe(
    instrument: str,
    step: str,
    night: str,
    config: str | None,
    sha: str | None,
    git_describe: str | None = None,
    lsst_version: str | None = None,
) -> str:
    cfg = f" --config {config}" if config else ""
    ver = git_describe or sha or "?"
    env = f", {lsst_version}" if lsst_version else ""
    return f"stips {step} {night}{cfg}  # stips @ {ver}{env}  (instrument={instrument})"


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


def load_store(path: Path) -> list[RunRecord]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [RunRecord.from_dict(d) for d in data]


def upsert_records(
    existing: list[RunRecord], incoming: list[RunRecord]
) -> list[RunRecord]:
    by_key = {r.key(): r for r in existing}
    for rec in incoming:
        by_key[rec.key()] = rec  # replace-or-add; never deletes others
    return sorted(
        by_key.values(),
        key=lambda r: (r.target, r.night, r.step, r.timestamp_end or ""),
    )


def save_store(path: Path, records: list[RunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([r.to_dict() for r in records], indent=2))


def _human_gb(n: int | None) -> str:
    return f"{n / 1e9:.1f} GB" if n else "—"


def render_markdown(records: list[RunRecord]) -> str:
    lines = [
        "# Pipeline Run Provenance",
        "",
        "_Generated from `provenance/runs.json` by `stips provenance sync`. "
        "Do not edit by hand._",
        "",
    ]
    targets: dict[str, list[RunRecord]] = {}
    for r in records:
        targets.setdefault(r.target, []).append(r)

    seen_repo_sizes: dict[str, int] = {}
    for target in sorted(targets):
        rows = targets[target]
        lines += [
            f"## {target}",
            "",
            "| repo | night | step | status | succ. exp | duration | size | repo | env | recipe |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in sorted(rows, key=lambda x: (x.night, x.step)):
            dur = (
                f"{r.duration_s}s{'~' if r.duration_approx else ''}"
                if r.duration_s
                else "—"
            )
            # Prefer the true pipelines version; fall back to the conda env name
            # for older records that predate lsst_pipelines_version.
            stack_ver = r.lsst_pipelines_version or r.lsst_stack_version or "?"
            env_cell = f"{stack_ver} / {r.stips_git_describe or r.stips_git_sha or '?'}"
            lines.append(
                f"| {r.repo} | {r.night} | {r.step} | {r.final_status} | "
                f"{r.successful_exposures} | {dur} | {_human_gb(r.repo_size_bytes)} | "
                f"{r.repo_status} | {env_cell} | `{r.rerun_recipe or ''}` |"
            )
            seen_repo_sizes[r.repo] = r.repo_size_bytes or 0
        lines.append("")

    total_bytes = sum(seen_repo_sizes.values())
    present = sum(
        s
        for repo, s in seen_repo_sizes.items()
        if any(r.repo == repo and r.repo_status == "present" for r in records)
    )
    lines += [
        "## Totals",
        "",
        f"- Runs recorded: {len(records)}",
        f"- Repos: {len(seen_repo_sizes)}",
        f"- On-disk (present repos): {_human_gb(present)}",
        f"- Tracked total (incl. reclaimed): {_human_gb(total_bytes)}",
        "",
    ]
    return "\n".join(lines)


def _iter_repos(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for plog_dir in sorted(root.glob("*/processing_log")):
            yield plog_dir.parent


def sync(
    roots: list[Path], out_dir: Path, repo_root: Path, dry_run: bool = False
) -> dict:
    incoming: list[RunRecord] = []
    repos_seen, empty_repos = [], []
    for repo in _iter_repos(roots):
        logs = sorted((repo / "processing_log").glob("*.json"))
        if not logs:
            empty_repos.append(repo.name)
            continue
        repos_seen.append(repo.name)
        size = repo_size_bytes(repo)
        lsst_ver = lsst_version_from_repo(repo)
        for lp in logs:
            try:
                rec = record_from_log_file(lp, repo)
            except (json.JSONDecodeError, KeyError):
                empty_repos.append(f"{repo.name}/{lp.name} (unparseable)")
                continue
            rec.repo_size_bytes = size
            rec.stips_git_sha = git_sha_before(repo_root, rec.timestamp_end)
            rec.stips_git_describe = git_describe(repo_root, rec.stips_git_sha)
            rec.lsst_stack_version = lsst_ver
            rec.lsst_stack_version_source = "repo-scan" if lsst_ver else None
            rec.duration_s = duration_from_stamps(rec.started_at, rec.ended_at)
            if rec.duration_s is None:
                rec.duration_approx = False
            cfg = rec.configs_tried[0]["config"] if rec.configs_tried else None
            rec.rerun_recipe = build_rerun_recipe(
                rec.instrument,
                rec.step,
                rec.night,
                cfg,
                rec.stips_git_sha,
                git_describe=rec.stips_git_describe,
                lsst_version=rec.lsst_stack_version,
            )
            incoming.append(rec)

    store = out_dir / "runs.json"
    existing = load_store(store)
    # A historical repo scan cannot know the pipelines version a past run used
    # (the live stack may have moved on), so `sync` never sets it. Preserve any
    # value a prior live `upsert_from_log` recorded, rather than clobbering it.
    prior_pipelines = {
        r.key(): r.lsst_pipelines_version for r in existing if r.lsst_pipelines_version
    }
    for rec in incoming:
        if rec.lsst_pipelines_version is None:
            rec.lsst_pipelines_version = prior_pipelines.get(rec.key())
    merged = upsert_records(existing, incoming)
    if not dry_run:
        save_store(store, merged)
        (out_dir / "RUNS.md").write_text(render_markdown(merged))
    return {
        "records": len(incoming),
        "repos": sorted(set(repos_seen)),
        "empty_or_unparseable": sorted(set(empty_repos)),
        "total_records_after": len(merged),
    }


def mark_deleted(repos: list[str], out_dir: Path, reclaimed_at: str) -> int:
    store = out_dir / "runs.json"
    records = load_store(store)
    targets = set(repos)
    n = 0
    for r in records:
        if r.repo in targets and r.repo_status != "deleted":
            r.repo_status = "deleted"
            r.reclaimed_at = reclaimed_at
            n += 1
    save_store(store, records)
    (out_dir / "RUNS.md").write_text(render_markdown(records))
    return n


def default_roots(config=None) -> list[Path]:
    """Data roots to scan for per-repo ``processing_log`` dirs.

    Precedence, no developer-specific defaults:
      1. ``STIPS_DATA_ROOTS`` env var (``os.pathsep``-separated absolute paths);
      2. the parent of the active Butler repo (``config.repo.parent``), when a
         ``Config`` is supplied — repos live side-by-side under this dir;
      3. otherwise log a WARNING and return an empty list (scan nothing).
    """
    env = os.environ.get("STIPS_DATA_ROOTS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    repo = getattr(config, "repo", None)
    if repo is not None:
        return [Path(repo).expanduser().parent]
    logging.getLogger(__name__).warning(
        "no data roots to scan: set STIPS_DATA_ROOTS (os.pathsep-separated "
        "absolute paths) or pass --roots; nothing will be scanned."
    )
    return []


def upsert_from_log(plog, config) -> None:
    """Live hook: upsert a single just-finished run. Never raises."""
    try:
        from stips.core.stack import stack_pipelines_version

        repo = Path(config.repo)
        repo_root = Path(__file__).resolve().parents[5]
        out_dir = repo_root / "provenance"
        log_path = repo / "processing_log" / f"{plog.night}_{plog.step}.json"
        # Instrument from the active profile (authoritative), not a path guess.
        rec = record_from_log_file(
            log_path, repo, instrument=instrument_from_config(config)
        )
        rec.repo_size_bytes = repo_size_bytes(repo)
        rec.stips_git_sha = git_sha_before(repo_root, rec.timestamp_end)
        rec.stips_git_describe = git_describe(repo_root, rec.stips_git_sha)
        _env_ver = lsst_version_from_env()
        rec.lsst_stack_version = _env_ver or lsst_version_from_repo(repo)
        rec.lsst_stack_version_source = (
            "env" if _env_ver else ("repo-scan" if rec.lsst_stack_version else None)
        )
        # True pipelines version (live, in-stack) alongside the conda-env name.
        rec.lsst_pipelines_version = stack_pipelines_version(config)
        rec.duration_s = duration_from_stamps(rec.started_at, rec.ended_at)
        cfg = rec.configs_tried[0]["config"] if rec.configs_tried else None
        rec.rerun_recipe = build_rerun_recipe(
            rec.instrument,
            rec.step,
            rec.night,
            cfg,
            rec.stips_git_sha,
            git_describe=rec.stips_git_describe,
            lsst_version=rec.lsst_pipelines_version or rec.lsst_stack_version,
        )
        save_store(
            out_dir / "runs.json",
            upsert_records(load_store(out_dir / "runs.json"), [rec]),
        )
        (out_dir / "RUNS.md").write_text(
            render_markdown(load_store(out_dir / "runs.json"))
        )
    except Exception:  # noqa: BLE001 — provenance must never break a pipeline run
        import logging

        logging.getLogger(__name__).warning("provenance upsert failed", exc_info=True)
