"""Execution backends for pipetask commands.

Provides an abstraction over how pipetask commands are executed, allowing
the same stage module code to run via direct subprocess (LocalExecutor)
or via BPS batch submission (BPSExecutor).

Stage modules call executor.run_pipetask() instead of stack.run_pipetask(),
preserving all existing stage-level logic (fallbacks, validation, etc.).
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from obs_nickel_data_tools.core import bps
from obs_nickel_data_tools.core.stack import run_butler_query, run_pipetask

if TYPE_CHECKING:

    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


@runtime_checkable
class PipetaskExecutor(Protocol):
    """Protocol for pipetask execution backends.

    Stage modules use this instead of calling run_pipetask() directly.
    The executor handles how the command is actually executed (local
    subprocess vs BPS submission).
    """

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess: ...


class LocalExecutor:
    """Execute pipetask commands via direct subprocess (current behavior).

    This is a passthrough to stack.run_pipetask() with zero behavior change.
    """

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        kwargs.pop("output_run", None)  # Only used by BPSExecutor
        return run_pipetask(args, config, **kwargs)


def _parse_pipetask_args(args: list[str]) -> dict:
    """Parse pipetask command-line args into a structured dict.

    Extracts key fields from pipetask qgraph/run argument lists so the
    BPSExecutor can map them to BPS configuration parameters.

    Args:
        args: Arguments as passed to pipetask (e.g., ["run", "-b", "/repo", ...])

    Returns:
        Dict with keys: subcommand, repo, qgraph_file, pipeline,
        input_collections, output_collection, output_run, data_query, jobs
    """
    parsed: dict = {
        "subcommand": args[0] if args else None,
        "repo": None,
        "qgraph_file": None,
        "pipeline": None,
        "input_collections": None,
        "output_collection": None,
        "output_run": None,
        "data_query": None,
        "jobs": None,
    }

    flag_map = {
        "-b": "repo",
        "-g": "qgraph_file",
        "-p": "pipeline",
        "-i": "input_collections",
        "-o": "output_collection",
        "-d": "data_query",
        "-j": "jobs",
        "--output-run": "output_run",
        "--save-qgraph": "save_qgraph",
    }

    i = 1  # Skip subcommand
    while i < len(args):
        if args[i] in flag_map and i + 1 < len(args):
            parsed[flag_map[args[i]]] = args[i + 1]
            i += 2
        else:
            i += 1

    return parsed


def _parse_bps_report(raw_output: str) -> dict:
    """Parse bps report tabular output into structured data.

    BPS report outputs a table with columns:
        X_REPORT  STATE  EXPECTED  SUCCEEDED  FAILED  UNREADY  READY  RUNNING

    We extract the 'summary' row.

    Args:
        raw_output: Raw text output from ``bps report <run_id>``

    Returns:
        Dict with state, expected, succeeded, failed, unready, ready, running
    """
    for line in raw_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("summary"):
            parts = stripped.split()
            if len(parts) >= 8:
                return {
                    "state": parts[1],
                    "expected": int(parts[2]),
                    "succeeded": int(parts[3]),
                    "failed": int(parts[4]),
                    "unready": int(parts[5]),
                    "ready": int(parts[6]),
                    "running": int(parts[7]),
                }
    return {
        "state": "UNKNOWN",
        "expected": 0,
        "succeeded": 0,
        "failed": 0,
        "unready": 0,
        "ready": 0,
        "running": 0,
    }


def _translate_bps_to_completed_process(
    bps_status: dict,
) -> subprocess.CompletedProcess:
    """Translate BPS status into a CompletedProcess.

    Stage modules parse CompletedProcess.stdout with _parse_quanta_summary()
    which looks for "Executed N quanta successfully, M failed out of total T".
    We format our stdout to match that pattern.

    Args:
        bps_status: Dict with state, succeeded, failed keys from _parse_bps_report()

    Returns:
        CompletedProcess with returncode and formatted stdout
    """
    state = bps_status.get("state", "UNKNOWN")
    quanta_ok = bps_status.get("succeeded", 0)
    quanta_fail = bps_status.get("failed", 0)
    total = quanta_ok + quanta_fail

    returncode = 0 if state == "SUCCEEDED" else 1

    stdout = (
        f"Executed {quanta_ok} quanta successfully, "
        f"{quanta_fail} failed out of total {total}"
    )

    return subprocess.CompletedProcess(
        args=["bps", "submit"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


class BPSExecutor:
    """Execute pipetask commands via BPS batch submission.

    QGraph generation ("qgraph" subcommand) always runs locally since it's
    fast and stage modules need to inspect the graph (e.g., empty qgraph check).

    Pipeline execution ("run" subcommand) is routed through BPS:
    1. Parse pipetask args to extract the pre-built qgraph file
    2. Build a BPSConfig and render the BPS YAML
    3. Submit via bps.submit()
    4. Poll via bps.status() until completion
    5. Translate BPS result to CompletedProcess for stage module compatibility

    Args:
        site: Compute site ("local", "slurm", "htcondor")
        poll_interval: Initial seconds between status checks (grows with backoff)
        timeout: Maximum seconds to wait for a single BPS job
    """

    def __init__(
        self,
        site: str = "local",
        poll_interval: float = 5.0,
        timeout: float = 7200.0,
    ):
        self.site = site
        self.poll_interval = poll_interval
        self.timeout = timeout

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        subcommand = args[0] if args else ""
        output_run = kwargs.pop("output_run", None)

        if subcommand == "qgraph":
            # QGraph generation runs locally (fast, needed for validation)
            return run_pipetask(args, config, **kwargs)

        if subcommand != "run":
            # Unknown subcommand — fall back to local execution
            return run_pipetask(args, config, **kwargs)

        return self._submit_and_poll(args, config, output_run=output_run, **kwargs)

    def _submit_and_poll(
        self,
        args: list[str],
        config: Config,
        *,
        output_run: str | None = None,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Submit a pipeline run to BPS and poll until completion."""
        parsed = _parse_pipetask_args(args)
        qgraph_file = parsed.get("qgraph_file")

        if not qgraph_file:
            log.warning("No qgraph file in args, falling back to local execution")
            return run_pipetask(args, config, **kwargs)

        if not output_run:
            log.warning(
                "No output_run provided to BPSExecutor — BPS will use default "
                "collection naming (u/{operator}/...) which may not match "
                "stage module expectations"
            )

        # Build BPSConfig for submission.
        # Derive a unique pipeline+night from the qgraph filename to avoid
        # FileExistsError when concurrent nights submit in the same second.
        # Qgraph filenames follow: processCcd_20230527_20260226T043651Z_cfg0.qg
        from pathlib import Path

        qg_stem = Path(qgraph_file).stem  # e.g. processCcd_20230527_..._cfg0
        bps_cfg = bps.BPSConfig(
            pipeline=qg_stem,
            night="0",
            site=self.site,
            qgraph_file=qgraph_file,
            output_run=output_run,
        )

        # Submit to BPS
        # NOTE: With Parsl backend, bps submit BLOCKS until the workflow
        # completes. The result already contains the final status.
        log.info(f"  Submitting to BPS (site={self.site}, qgraph={qgraph_file})")
        bps_result = bps.submit(bps_cfg, config)

        if not bps_result.success:
            log.error(f"  BPS submit failed: {bps_result.error}")
            return subprocess.CompletedProcess(
                args=["bps", "submit"],
                returncode=1,
                stdout=bps_result.stdout or "",
                stderr=bps_result.error or "BPS submission failed",
            )

        run_id = bps_result.run_id
        log.info(f"  BPS job completed: run_id={run_id}")

        stdout = bps_result.stdout or ""
        stderr = bps_result.stderr or ""

        # Determine success by checking if the output_run collection was
        # created in Butler. This is the definitive test: pipetask run-qbb
        # only creates the RUN collection when at least one quantum produces
        # output. If all quanta fail, no collection is registered.
        #
        # Previous approaches (parsing finalJob.stderr for "Ingested N
        # dataset(s)") were unreliable because: (a) bps_result.submit_dir
        # doesn't match BPS's actual submitPath, and (b) globbing for the
        # most recent submit directory picks up logs from prior runs.
        repo = parsed.get("repo", "")
        if output_run and repo:
            verify = run_butler_query(
                ["query-collections", repo, output_run],
                config,
                check=False,
            )
            collection_exists = verify.returncode == 0 and output_run in (
                verify.stdout or ""
            )

            if collection_exists:
                log.info(f"  RUN collection {output_run} verified in Butler")
                return subprocess.CompletedProcess(
                    args=["bps", "submit"],
                    returncode=0,
                    stdout=(
                        "Executed 1 quanta successfully, "
                        "0 failed out of total 1\n" + stdout
                    ),
                    stderr=stderr,
                )
            else:
                log.warning(
                    f"  BPS job completed but RUN collection {output_run} "
                    f"not found in Butler — all quanta may have failed"
                )
                return subprocess.CompletedProcess(
                    args=["bps", "submit"],
                    returncode=1,
                    stdout=(
                        "Executed 0 quanta successfully, "
                        "0 failed out of total 0\n" + stdout
                    ),
                    stderr=stderr,
                )

        # Fallback: no output_run provided — can't verify collection.
        # Return success since bps.submit() reported success.
        log.warning("  No output_run to verify — trusting BPS exit status")
        return subprocess.CompletedProcess(
            args=["bps", "submit"],
            returncode=0,
            stdout=stdout,
            stderr=stderr,
        )
