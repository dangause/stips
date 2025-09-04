from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import optuna

from .context import Context
from .butler_utils import discover_postisr, discover_all_science_visits
from .objective import make_objective

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Tune Nickel calibrateImage with failure-penalized scoring"
    )
    p.add_argument("--repo", required=True, help="Butler repo path")
    p.add_argument("--obs-nickel", required=True, help="obs_nickel package root")
    p.add_argument("--visits", nargs="+", type=int, help="visit IDs to process (omit to use all)")
    p.add_argument("--bad", nargs="*", type=int, default=[], help="visits to exclude")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--workdir", required=True, help="directory to store trial artifacts & tables")
    p.add_argument("--proc-pipe", default=None, help="ProcessCcd.yaml path; default uses obs-nickel/pipelines/ProcessCcd.yaml")
    p.add_argument("--post-pipe", default=None, help="PostProcessing.yaml path; default uses obs-nickel/pipelines/PostProcessing.yaml")
    p.add_argument("--inputs-postisr", default=None, help="postISR input collection (e.g., Nickel/run/processCcd/...)")
    p.add_argument("--calib-chain", default="Nickel/calib/current")
    p.add_argument("--refcats", default="refcats")
    p.add_argument("--fail-policy", choices=["hard","frac","linear"], default="frac")
    p.add_argument("--fail-weight", type=float, default=1.0)
    p.add_argument("--echo-logs", action="store_true", help="Echo tail of stdout/stderr for each pipetask")
    p.add_argument("--tail", type=int, default=20, help="Number of lines to tail when echoing logs")
    p.add_argument("--no-postproc", action="store_true", help="Skip PostProcessing.yaml (default: run it)")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    repo = Path(args.repo)
    obs = Path(args.obs_nickel)
    proc_pipe = Path(args.proc_pipe) if args.proc_pipe else obs / "pipelines" / "ProcessCcd.yaml"
    post_pipe = Path(args.post_pipe) if args.post_pipe else obs / "pipelines" / "PostProcessing.yaml"
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    inputs_postisr = args.inputs_postisr or discover_postisr(repo)
    if not inputs_postisr:
        print("[inputs] Could not discover postISR collection automatically; specify --inputs-postisr", file=sys.stderr)
        sys.exit(2)

    # Resolve visits: explicit list or discover all science visits
    if args.visits and len(args.visits) > 0:
        visits = [v for v in args.visits if v not in set(args.bad)]
        discovered_note = ""
    else:
        all_visits = discover_all_science_visits(repo)
        visits = [v for v in all_visits if v not in set(args.bad)]
        discovered_note = f" (auto-discovered {len(all_visits)})"

    print(f"[inputs] postISR: {inputs_postisr}")
    print(f"[inputs] calib  : {args.calib_chain}")
    print(f"[inputs] proc   : {proc_pipe}")
    print(f"[inputs] post   : {post_pipe}")
    print(f"[inputs] visits : {visits}{discovered_note} (excluded {args.bad})")

    ctx = Context(
        repo=repo,
        obs_nickel=obs,
        proc_pipe=proc_pipe,
        post_pipe=post_pipe,
        workdir=workdir,
        visits=visits,
        bad=args.bad,
        jobs=args.jobs,
        inputs_postisr=inputs_postisr,
        calib_chain=args.calib_chain,
        refcats=args.refcats,
        fail_policy=args.fail_policy,
        fail_weight=args.fail_weight,
        echo_logs=args.echo_logs,
        tail=args.tail,
        run_postproc=(not args.no_postproc),
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

if __name__ == "__main__":
    main()
