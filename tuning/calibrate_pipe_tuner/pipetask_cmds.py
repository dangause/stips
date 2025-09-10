from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .context import Context
from .io_utils import run, tail_lines
from .io_utils import ensure_parent
from .io_utils import now_utc_iso
from .io_utils import write_csv_row
from .context import FAIL_LOG_HEADERS

def build_calibrate_cmd(ctx: Context, overrides: Path, visit: int, out_coll: str) -> List[str]:
    """Build a pipetask run command for calibrateImage on a single visit."""
    return [
        "pipetask", "run",
        "-b", str(ctx.repo),
        "-i", ",".join([ctx.inputs_postisr, ctx.calib_chain, ctx.refcats]),
        "-o", out_coll,
        "-p", str(ctx.proc_pipe) + "#calibrateImage",
        "-C", f"calibrateImage:{overrides}",
        "-j", str(ctx.jobs),
        "--register-dataset-types",
        "-d", f"instrument='Nickel' AND exposure.observation_type='science' AND visit IN ({int(visit)})",
    ]

def build_postproc_cmd(ctx: Context, out_coll: str, post_out: str, visits: List[int]) -> List[str]:
    """Build a pipetask run command for PostProcessing over multiple visits."""
    vlist = ",".join(str(int(v)) for v in visits)
    return [
        "pipetask", "run",
        "-b", str(ctx.repo),
        "-i", ",".join([out_coll, ctx.calib_chain, ctx.refcats]),
        "-o", post_out,
        "-p", str(ctx.post_pipe),
        "--register-dataset-types",
        "-j", str(ctx.jobs),
        "-d", (
            "instrument='Nickel' AND detector=0 AND exposure.observation_type='science' "
            f"AND visit IN ({vlist})"
        ),
    ]

def log_failure_row(workdir: Path, tag: str, exc: BaseException, cmd: List[str],
                    stdout_log: Optional[Path], stderr_log: Optional[Path]) -> None:
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

def maybe_run_postproc(ctx: Context, out_coll: str, trial_dir: Path, visits: List[int]) -> Optional[str]:
    """Run PostProcessing.yaml into a timestamped child collection. Return its name or None on failure."""
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
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
        log_failure_row(ctx.workdir, f"{out_coll}-postproc", e, cmd, stdout_log, stderr_log)
        print(f"\n--- postproc FAILED ---")
        return None
