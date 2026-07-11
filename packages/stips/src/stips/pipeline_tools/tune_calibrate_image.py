#!/usr/bin/env python
"""Tune ``calibrateImage`` config parameters over pipetask runs (framework tool).

Framework tool (``stips-tune-calibrate-image``). This is the instrument-neutral
extraction of the former ``obs-nickel-tuning`` package (``calibrate_pipe_tuner``):
the *tuning harness* -- an Optuna search that samples ``calibrateImage`` config
parameters from a ``tune.yaml``, runs ``pipetask`` per visit, scores the
resulting ``visitSummary`` metrics, and records every trial -- is framework code
parameterized by the active instrument profile. An instrument's *tuned* configs
(the winning overrides) live under its own tree at
``instruments/<name>/configs/calibrateImage/tuned_configs/``.

Algorithm (unchanged from the Nickel original)
----------------------------------------------
1. Load a ``tune.yaml`` defining the parameter search space (``parameters``),
   the scoring ``metrics`` (field / aggregate / direction / target / weight), and
   a static ``overrides_prelude`` injected into every trial's config.
2. For each Optuna trial: sample parameters, write a per-trial ``calibrateImage``
   overrides file, run ``pipetask run`` on each science visit, optionally run a
   post-processing pipeline, read ``visitSummary`` metric medians, and combine
   them into a single score (min-direction ``weight*value/target``, max-direction
   ``weight*target/value``) with a failure penalty (hard / frac / linear).
3. Persist every trial (``tuning_runs.csv``, ``trial_failures.csv``, per-trial
   ``metrics.json`` + overrides) and print the best trial as JSON. The winning
   overrides file is what you commit under the instrument's ``tuned_configs/``.

Parameterization
----------------
The instrument name (Butler queries, ``pipetask -d instrument=...``) and the
collection prefix (default input/output collection names) come from the active
profile (``INSTRUMENT_DIR``), overridable with ``--instrument`` /
``--collection-prefix``. The search space, metrics, and prelude are entirely
data-driven from the ``--config`` YAML -- nothing about them is Nickel-specific.

Producing tuned configs for a NEW instrument
--------------------------------------------
1. Process a set of science visits (``stips science``) so postISR + calib inputs
   exist.
2. Write a ``tune.yaml`` for your camera's ``calibrateImage`` knobs and metric
   targets (start from ``instruments/nickel/tuning/tune.yaml``).
3. Run ``stips-tune-calibrate-image --repo $REPO --pipeline-dir <dir with
   pipelines/ProcessCcd.yaml> --workdir <out> --config tune.yaml --trials N``.
4. Commit the best trial's overrides file under
   ``instruments/<name>/configs/calibrateImage/tuned_configs/`` and record the
   invocation in ``instruments/<name>/tuning/README.md``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# optuna and lsst.* are imported lazily (inside main()/make_objective and the
# butler helpers) so ``--help`` and the unit tests run in a plain venv.

# ------------------------------- io helpers ----------------------------


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def tail_lines(s: str, n: int) -> str:
    if not s:
        return ""
    lines = s.rstrip("\n").splitlines()
    return "\n".join(lines[-n:]) if n > 0 else s


def run(
    cmd: List[str],
    check: bool,
    stdout_log: Optional[Path] = None,
    stderr_log: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess, tee stdout/stderr into files (if provided)."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = proc.communicate()
    if stdout_log:
        ensure_parent(stdout_log)
        stdout_log.write_text(out or "")
    if stderr_log:
        ensure_parent(stderr_log)
        stderr_log.write_text(err or "")
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=out, stderr=err
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def write_csv_row(csv_path: Path, headers: List[str], row: Dict[str, Any]) -> None:
    ensure_parent(csv_path)
    new = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if new:
            w.writeheader()
        safe = {h: row.get(h, "") for h in headers}
        w.writerow(safe)


# ------------------------------- config IO -----------------------------


def load_config(path: Path) -> Dict[str, Any]:
    """Load tuning config from YAML or JSON."""
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except Exception as exc:  # pragma: no cover - yaml is a hard dep
            raise RuntimeError(
                "PyYAML not installed; install pyyaml or use JSON."
            ) from exc
        return yaml.safe_load(text) or {}
    return json.loads(text)


# ------------------------------- context -------------------------------

FAIL_LOG_HEADERS = [
    "time",
    "trial_tag",
    "exception",
    "message",
    "returncode",
    "cmd",
    "stdout_log",
    "stderr_log",
]


@dataclass
class Context:
    """Immutable runtime configuration shared across the tuning run."""

    repo: Path
    pipeline_dir: Path
    proc_pipe: Path
    post_pipe: Path
    workdir: Path
    visits: List[int]  # resolved visit list to process
    bad: List[int]  # visits explicitly excluded
    jobs: int
    inputs_postisr: str  # e.g. "<prefix>/run/processCcd/<timestamp>"
    calib_chain: str  # e.g. "<prefix>/calib/current"
    refcats: str  # usually "refcats"
    fail_policy: str  # "hard" | "frac" | "linear"
    fail_weight: float
    echo_logs: bool
    tail: int
    run_postproc: bool
    cfg: dict  # loaded tune config (parameters + metrics)
    instrument: str  # Butler instrument name for queries / pipetask -d
    prefix: str  # collection prefix (e.g. "Nickel")


def make_runs_headers(ctx: Context) -> List[str]:
    """Build CSV headers including dynamic metric names and parameter keys."""
    metric_names = [m["name"] for m in ctx.cfg.get("metrics", [])]
    param_keys = list(ctx.cfg.get("parameters", {}).keys())
    return [
        "time",
        "trial_index",
        "trial_tag",
        "status",
        "out_coll",
        "read_from_collection",
        "postproc_out",
        "n_total",
        "n_success",
        "n_fail",
        "success_rate",
        *metric_names,
        "score_base",
        "score",
        *param_keys,
        "overrides_path",
        "trial_dir",
    ]


# ------------------------------- bounds --------------------------------


def suggest_params(trial: Any, param_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Sample params based on config (``trial`` = an Optuna trial or stub)."""
    out: Dict[str, Any] = {}
    for name, spec in param_cfg.items():
        typ = spec["type"]
        if typ == "float":
            out[name] = trial.suggest_float(
                name, float(spec["low"]), float(spec["high"])
            )
        elif typ == "int":
            out[name] = trial.suggest_int(name, int(spec["low"]), int(spec["high"]))
        elif typ == "categorical":
            out[name] = trial.suggest_categorical(name, list(spec["choices"]))
        else:
            raise ValueError(f"Unknown param type for {name}: {typ}")
    return out


# ------------------------------ overrides ------------------------------


def write_overrides_from_config(
    workdir: Path,
    tag: str,
    params: Dict[str, float],
    param_cfg: Dict[str, dict],
    prelude: str = "",
) -> Path:
    """Emit per-trial overrides from config (one 'apply' snippet per parameter)."""
    trial_dir = workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)
    ov_path = trial_dir / f"calib_overrides_{tag}.py"

    lines = [
        "# Auto-generated overrides for " + tag,
        "# Executed with `config` in scope.",
        "",
    ]
    if prelude.strip():
        lines.append("# ---- Prelude ----")
        lines.append(prelude.rstrip("\n"))
        lines.append("")

    lines.append("# ---- Tuned Parameters ----")
    for name, value in params.items():
        apply_line = param_cfg[name]["apply"]
        # substitute {value} with a representation that preserves ints/floats
        val_repr = repr(value) if not isinstance(value, float) else f"{value:.8g}"
        lines.append(f"# {name}")
        lines.append(apply_line.format(value=val_repr))

    ensure_parent(ov_path)
    ov_path.write_text("\n".join(lines) + "\n")
    return ov_path


# ------------------------------- scoring -------------------------------


def aggregate(values: List[float], how: str) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    if how == "median":
        n = len(v)
        return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])
    if how == "mean":
        return sum(v) / len(v)
    raise ValueError(f"Unknown aggregate: {how}")


def compute_metrics_and_score(
    meds: Dict[str, Optional[float]],
    metrics_cfg: List[dict],
) -> Tuple[float, float]:
    """Combine metric medians into a base score (config-driven targets/weights).

    Min-direction term = ``weight * (value / target)``; max-direction term =
    ``weight * (target / value)``. Any missing/non-positive metric => ``inf``.
    Returns a legacy pair ``(score_base, score_base)`` (failure penalty applied
    separately in :func:`penalize_score`).
    """
    total = 0.0
    for m in metrics_cfg:
        name = m["name"]
        target = float(m["target"])
        weight = float(m["weight"])
        direction = m["direction"]  # 'min' or 'max'
        val = meds.get(name)
        if val is None or val <= 0 or target <= 0:
            return math.inf, math.inf
        if direction == "min":
            term = weight * (val / target)
        elif direction == "max":
            term = weight * (target / val)
        else:
            raise ValueError(f"direction must be 'min' or 'max' for {name}")
        total += term
    return total, total


def penalize_score(
    base_score: float,
    n_success: int,
    n_total: int,
    policy: str = "frac",
    weight: float = 1.0,
) -> float:
    """Apply failure-penalization to a base score.

    hard   : any failure => +inf
    frac   : base * (success_rate ** -weight)
    linear : base * (1 + weight * n_fail)
    """
    if n_total <= 0:
        return math.inf

    n_fail = n_total - n_success

    if policy == "hard":
        return math.inf if n_fail > 0 else base_score

    if policy == "frac":
        sr = n_success / n_total
        if sr <= 0:
            return math.inf
        return base_score * (sr ** (-weight))

    if policy == "linear":
        return base_score * (1.0 + weight * n_fail)

    # Unknown policy -> no extra penalty
    return base_score


# ---------------------------- butler helpers ---------------------------
# lsst.daf.butler is imported lazily so the module imports in a plain venv.


def discover_postisr(repo: Path, prefix: str) -> str:
    """Return latest ``<prefix>/run/processCcd/*`` run collection, or '' if none."""
    from lsst.daf.butler import Butler

    b = Butler(str(repo))
    needle = f"{prefix}/run/processCcd/"
    cands = [
        str(rec) for rec in b.registry.queryCollections() if str(rec).startswith(needle)
    ]
    return sorted(cands)[-1] if cands else ""


def discover_all_science_visits(repo: Path, instrument: str) -> List[int]:
    """Return all visit IDs for the instrument's science exposures in this repo."""
    from lsst.daf.butler import Butler

    b = Butler(str(repo))

    try:
        recs = b.registry.queryDimensionRecords(
            "visit",
            where=(
                f"instrument='{instrument}' AND " "exposure.observation_type='science'"
            ),
        )
        return sorted(int(r.id) for r in recs)
    except Exception:
        pass

    try:
        q = b.registry.queryDataIds(
            dimensions={"instrument", "visit", "detector"},
            datasets="raw",
            where=(
                f"instrument='{instrument}' AND " "exposure.observation_type='science'"
            ),
        )
        visits = {int(d["visit"]) for d in q}
        return sorted(visits)
    except Exception as e:
        raise RuntimeError(
            f"Could not discover visits automatically: {e}\n"
            "Try specifying --visits explicitly."
        )


def read_visit_summaries(
    coll: str, repo: Path, visits: List[int], instrument: str
) -> List[Any]:
    from lsst.daf.butler import Butler

    butler = Butler(str(repo), collections=coll, instrument=instrument)
    rows: List[Any] = []
    for v in visits:
        try:
            vs = butler.get("visitSummary", {"instrument": instrument, "visit": int(v)})
            tbl = vs.asAstropy()
            if len(tbl) > 0:
                rows.append(tbl[0])
        except Exception:
            pass
    return rows


def extract_metric_values(rows: List[Any], field: str) -> List[float]:
    vals: List[float] = []
    for r in rows:
        try:
            vals.append(float(r[field]))
        except Exception:
            pass
    return vals


# ---------------------------- pipetask commands ------------------------


def build_calibrate_cmd(
    ctx: Context, overrides: Path, visit: int, out_coll: str
) -> List[str]:
    """Build a pipetask run command for calibrateImage on a single visit."""
    return [
        "pipetask",
        "run",
        "-b",
        str(ctx.repo),
        "-i",
        ",".join([ctx.inputs_postisr, ctx.calib_chain, ctx.refcats]),
        "-o",
        out_coll,
        "-p",
        str(ctx.proc_pipe) + "#calibrateImage",
        "-C",
        f"calibrateImage:{overrides}",
        "-j",
        str(ctx.jobs),
        "--register-dataset-types",
        "-d",
        (
            f"instrument='{ctx.instrument}' AND "
            f"exposure.observation_type='science' AND visit IN ({int(visit)})"
        ),
    ]


def build_postproc_cmd(
    ctx: Context, out_coll: str, post_out: str, visits: List[int]
) -> List[str]:
    """Build a pipetask run command for PostProcessing over multiple visits."""
    vlist = ",".join(str(int(v)) for v in visits)
    return [
        "pipetask",
        "run",
        "-b",
        str(ctx.repo),
        "-i",
        ",".join([out_coll, ctx.calib_chain, ctx.refcats]),
        "-o",
        post_out,
        "-p",
        str(ctx.post_pipe),
        "--register-dataset-types",
        "-j",
        str(ctx.jobs),
        "-d",
        (
            f"instrument='{ctx.instrument}' AND detector=0 AND "
            f"exposure.observation_type='science' AND visit IN ({vlist})"
        ),
    ]


def log_failure_row(
    workdir: Path,
    tag: str,
    exc: BaseException,
    cmd: List[str],
    stdout_log: Optional[Path],
    stderr_log: Optional[Path],
) -> None:
    """Append a failure row to trial_failures.csv."""
    row = {
        "time": now_utc_iso(),
        "trial_tag": tag,
        "exception": exc.__class__.__name__,
        "message": str(exc),
        "returncode": getattr(exc, "returncode", ""),
        "cmd": " ".join(cmd),
        "stdout_log": str(stdout_log) if stdout_log else "",
        "stderr_log": str(stderr_log) if stderr_log else "",
    }
    write_csv_row(workdir / "trial_failures.csv", FAIL_LOG_HEADERS, row)


def maybe_run_postproc(
    ctx: Context, out_coll: str, trial_dir: Path, visits: List[int]
) -> Optional[str]:
    """Run PostProcessing into a timestamped child collection; name or None."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    post_out = f"{out_coll}/{ts}"
    cmd = build_postproc_cmd(ctx, out_coll, post_out, visits)
    stdout_log = trial_dir / "postproc_stdout.log"
    stderr_log = trial_dir / "postproc_stderr.log"
    try:
        cp = run(cmd, check=True, stdout_log=stdout_log, stderr_log=stderr_log)
        if ctx.echo_logs:
            print("\n--- postproc (rc=0) tail ---")
            print(tail_lines(cp.stdout, ctx.tail))
            if cp.stderr:
                print("--- STDERR tail ---")
                print(tail_lines(cp.stderr, ctx.tail))
        return post_out
    except Exception as e:
        log_failure_row(
            ctx.workdir, f"{out_coll}-postproc", e, cmd, stdout_log, stderr_log
        )
        print("\n--- postproc FAILED ---")
        return None


# ------------------------------- runner --------------------------------


def run_trial(
    ctx: Context, params: Dict[str, float], tag: str, trial_index: int
) -> Tuple[str, float, Dict[str, float]]:
    trial_dir = ctx.workdir / "trials" / tag
    trial_dir.mkdir(parents=True, exist_ok=True)

    ov_path = write_overrides_from_config(
        ctx.workdir,
        tag,
        params,
        ctx.cfg["parameters"],
        ctx.cfg.get("overrides_prelude", ""),
    )

    out_coll = f"{ctx.prefix}/run/calib_tune/{tag}"

    success_visits: List[int] = []
    failed_visits: List[int] = []

    # Run calibrateImage per-visit
    for v in ctx.visits:
        cmd = build_calibrate_cmd(ctx, ov_path, v, out_coll)
        stdout_log = trial_dir / f"v{v}_stdout.log"
        stderr_log = trial_dir / f"v{v}_stderr.log"
        try:
            cp = run(cmd, check=True, stdout_log=stdout_log, stderr_log=stderr_log)
            if ctx.echo_logs:
                print(
                    f"\n--- pipetask calibrateImage v{v} (rc={cp.returncode}) tail ---"
                )
                if cp.stdout:
                    print(tail_lines(cp.stdout, ctx.tail))
                if cp.stderr:
                    print("\n--- STDERR tail ---")
                    print(tail_lines(cp.stderr, ctx.tail))
            success_visits.append(v)
        except Exception as e:
            log_failure_row(ctx.workdir, f"{tag}-v{v}", e, cmd, stdout_log, stderr_log)
            failed_visits.append(v)

    n_total = len(ctx.visits)
    n_success = len(success_visits)
    if n_success == 0:
        raise RuntimeError("All visits failed in this trial")

    # Optional post-processing
    post_coll = None
    if ctx.run_postproc:
        post_coll = maybe_run_postproc(ctx, out_coll, trial_dir, success_visits)
    read_coll = post_coll if post_coll is not None else out_coll

    # Build metric medians dynamically from config
    rows = read_visit_summaries(read_coll, ctx.repo, success_visits, ctx.instrument)
    meds: Dict[str, float] = {}
    for m in ctx.cfg["metrics"]:
        vals = extract_metric_values(rows, m["field"])
        meds[m["name"]] = aggregate(vals, m.get("aggregate", "median"))

    score_base, _ = compute_metrics_and_score(meds, ctx.cfg["metrics"])
    score = penalize_score(
        score_base, n_success, n_total, ctx.fail_policy, ctx.fail_weight
    )

    metrics = {
        "n_total": n_total,
        "n_success": n_success,
        "n_fail": n_total - n_success,
        "success_rate": n_success / n_total if n_total > 0 else 0.0,
        **meds,
        "score_base": score_base,
        "score": score,
    }

    # Write per-trial JSON
    (trial_dir / "metrics.json").write_text(
        json.dumps(
            {
                "time": now_utc_iso(),
                "trial_index": trial_index,
                "trial_tag": tag,
                "out_coll": out_coll,
                "read_from_collection": read_coll,
                "postproc_out": post_coll,
                "params": params,
                "metrics": metrics,
                "success_visits": success_visits,
                "failed_visits": failed_visits,
                "overrides_path": str(ov_path),
            },
            indent=2,
        )
    )

    # Runs CSV (dynamic headers)
    headers = make_runs_headers(ctx)
    row = {
        "time": now_utc_iso(),
        "trial_index": trial_index,
        "trial_tag": tag,
        "status": (
            "ok" if n_success == n_total else ("partial" if n_success > 0 else "fail")
        ),
        "out_coll": out_coll,
        "read_from_collection": read_coll,
        "postproc_out": post_coll or "",
        "n_total": n_total,
        "n_success": n_success,
        "n_fail": n_total - n_success,
        "success_rate": metrics["success_rate"],
        **{m["name"]: metrics.get(m["name"], "") for m in ctx.cfg["metrics"]},
        "score_base": metrics["score_base"],
        "score": metrics["score"],
        **{k: params.get(k, "") for k in ctx.cfg["parameters"].keys()},
        "overrides_path": str(ov_path),
        "trial_dir": str(trial_dir),
    }
    write_csv_row(ctx.workdir / "tuning_runs.csv", headers, row)

    return out_coll, score, metrics


# ------------------------------ objective ------------------------------


def make_objective(ctx: Context):
    import optuna

    def objective(trial: "optuna.Trial") -> float:
        params = suggest_params(trial, ctx.cfg["parameters"])
        tag = f"t{trial.number:03d}"
        try:
            out_coll, score, metrics = run_trial(ctx, params, tag, trial.number)
            trial.set_user_attr("out_coll", out_coll)
            trial.set_user_attr("metrics", metrics)
            trial.set_user_attr("params", params)
            return score
        except Exception as e:
            headers = make_runs_headers(ctx)
            write_csv_row(
                ctx.workdir / "tuning_runs.csv",
                headers,
                {
                    "time": now_utc_iso(),
                    "trial_index": trial.number,
                    "trial_tag": tag,
                    "status": "fail",
                    "out_coll": "",
                    "read_from_collection": "",
                    "postproc_out": "",
                    "n_total": len(ctx.visits),
                    "n_success": 0,
                    "n_fail": len(ctx.visits),
                    "success_rate": 0.0,
                    **{m["name"]: "" for m in ctx.cfg["metrics"]},
                    "score_base": "",
                    "score": "",
                    **{k: params.get(k, "") for k in ctx.cfg["parameters"].keys()},
                    "overrides_path": "",
                    "trial_dir": str(ctx.workdir / "trials" / tag),
                },
            )
            raise optuna.TrialPruned(f"Trial error: {e}")

    return objective


# ------------------------------- CLI -----------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Tune calibrateImage config parameters via an Optuna search over "
            "pipetask runs (instrument-neutral; parameterized by the active profile)."
        )
    )
    p.add_argument("--repo", required=True, help="Butler repo path")
    p.add_argument(
        "--pipeline-dir",
        required=True,
        help="Directory containing pipelines/ProcessCcd.yaml (+ PostProcessing.yaml).",
    )
    p.add_argument(
        "--instrument",
        default=None,
        help="Instrument name for Butler queries (default: active profile name).",
    )
    p.add_argument(
        "--collection-prefix",
        default=None,
        help="Collection prefix for default collection names (default: profile).",
    )
    p.add_argument(
        "--visits", nargs="+", type=int, help="visit IDs to process (omit to use all)"
    )
    p.add_argument("--bad", nargs="*", type=int, default=[], help="visits to exclude")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument(
        "--workdir", required=True, help="directory to store trial artifacts & tables"
    )
    p.add_argument(
        "--proc-pipe",
        default=None,
        help="ProcessCcd.yaml path; default <pipeline-dir>/pipelines/ProcessCcd.yaml",
    )
    p.add_argument(
        "--post-pipe",
        default=None,
        help="PostProcessing.yaml path; default <pipeline-dir>/pipelines/PostProcessing.yaml",
    )
    p.add_argument(
        "--inputs-postisr",
        default=None,
        help="postISR input collection (e.g. <prefix>/run/processCcd/...)",
    )
    p.add_argument(
        "--calib-chain",
        default=None,
        help="Calib chain collection (default: <prefix>/calib/current)",
    )
    p.add_argument("--refcats", default="refcats")
    p.add_argument("--fail-policy", choices=["hard", "frac", "linear"], default="frac")
    p.add_argument("--fail-weight", type=float, default=1.0)
    p.add_argument(
        "--echo-logs",
        action="store_true",
        help="Echo tail of stdout/stderr for each pipetask",
    )
    p.add_argument(
        "--tail", type=int, default=20, help="Number of lines to tail when echoing logs"
    )
    p.add_argument(
        "--no-postproc",
        action="store_true",
        help="Skip PostProcessing.yaml (default: run it)",
    )
    p.add_argument(
        "--config",
        required=True,
        help="Path to tune.yaml (or .json) defining parameters & metrics",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    import optuna

    from stips.pipeline_tools._profile_resolve import (
        resolve_collection_prefix,
        resolve_instrument_name,
    )

    instrument = resolve_instrument_name(args.instrument)
    prefix = args.collection_prefix or resolve_collection_prefix(args.instrument)

    repo = Path(args.repo)
    pdir = Path(args.pipeline_dir)
    proc_pipe = (
        Path(args.proc_pipe)
        if args.proc_pipe
        else pdir / "pipelines" / "ProcessCcd.yaml"
    )
    post_pipe = (
        Path(args.post_pipe)
        if args.post_pipe
        else pdir / "pipelines" / "PostProcessing.yaml"
    )
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    inputs_postisr = args.inputs_postisr or discover_postisr(repo, prefix)
    if not inputs_postisr:
        print(
            "[inputs] Could not discover postISR collection automatically; "
            "specify --inputs-postisr",
            file=sys.stderr,
        )
        return 2
    calib_chain = args.calib_chain or f"{prefix}/calib/current"

    # Resolve visits: explicit list or discover all science visits
    if args.visits and len(args.visits) > 0:
        visits = [v for v in args.visits if v not in set(args.bad)]
        discovered_note = ""
    else:
        all_visits = discover_all_science_visits(repo, instrument)
        visits = [v for v in all_visits if v not in set(args.bad)]
        discovered_note = f" (auto-discovered {len(all_visits)})"

    print(f"[inputs] instrument: {instrument} (prefix {prefix})")
    print(f"[inputs] postISR: {inputs_postisr}")
    print(f"[inputs] calib  : {calib_chain}")
    print(f"[inputs] proc   : {proc_pipe}")
    print(f"[inputs] post   : {post_pipe}")
    print(f"[inputs] visits : {visits}{discovered_note} (excluded {args.bad})")

    cfg = load_config(Path(args.config))

    ctx = Context(
        repo=repo,
        pipeline_dir=pdir,
        proc_pipe=proc_pipe,
        post_pipe=post_pipe,
        workdir=workdir,
        visits=visits,
        bad=args.bad,
        jobs=args.jobs,
        inputs_postisr=inputs_postisr,
        calib_chain=calib_chain,
        refcats=args.refcats,
        fail_policy=args.fail_policy,
        fail_weight=args.fail_weight,
        echo_logs=args.echo_logs,
        tail=args.tail,
        run_postproc=(not args.no_postproc),
        cfg=cfg,
        instrument=instrument,
        prefix=prefix,
    )

    study = optuna.create_study(direction="minimize")
    study.optimize(make_objective(ctx), n_trials=args.trials, show_progress_bar=True)

    best = study.best_trial
    print("\n=== BEST TRIAL ===")
    out = {
        "value": best.value,
        "params": best.user_attrs.get("params", best.params),
        "metrics": best.user_attrs.get("metrics", {}),
        "out_coll": best.user_attrs.get("out_coll", ""),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
