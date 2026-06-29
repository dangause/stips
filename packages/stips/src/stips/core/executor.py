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
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from stips.core import bps, bps_report, butler_query
from stips.core.stack import run_pipetask

if TYPE_CHECKING:

    from stips.core.config import Config

log = logging.getLogger(__name__)


@runtime_checkable
class PipetaskExecutor(Protocol):
    """Protocol for pipetask execution backends.

    Stage modules use this instead of calling run_pipetask() directly.
    The executor handles how the command is actually executed (local
    subprocess vs BPS submission).
    """

    @property
    def needs_datastore_records(self) -> bool:
        """Whether qgraphs need --qgraph-datastore-records.

        BPS run-qbb requires datastore records embedded in the qgraph.
        Local pipetask run resolves records from the Butler directly,
        and embedding records can strip columns from non-standard
        catalogs (e.g. MONSTER refcat loads only 3 fields instead of 82).
        """
        ...

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

    needs_datastore_records = False

    # kwargs accepted by stack.run_pipetask()
    _PASSTHROUGH_KWARGS = {"capture_output", "check", "log_file", "log_level"}

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        # Strip kwargs only used by BPSExecutor (e.g. output_run)
        filtered = {k: v for k, v in kwargs.items() if k in self._PASSTHROUGH_KWARGS}
        return run_pipetask(args, config, **filtered)


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


def _check_output_collection(output_run: str, config: Config) -> bool:
    """Check if a Butler output_run collection has actual datasets.

    BPS infrastructure may create an empty RUN collection before quanta
    execute, so checking collection existence alone is insufficient. The
    collection's dataset-type summary is non-empty only when quanta produced
    output, so it answers exists-and-non-empty in one structured query.
    """
    if not output_run:
        return False
    return butler_query.collection_has_datasets(config, output_run)


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

    needs_datastore_records = True

    def __init__(
        self,
        site: str = "local",
        poll_interval: float = 5.0,
        timeout: float = 7200.0,
        container_image: str | None = None,
    ):
        self.site = site
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.container_image = container_image

    def run_pipetask(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        subcommand = args[0] if args else ""

        if subcommand == "qgraph":
            # QGraph generation runs locally (fast, needed for validation)
            return run_pipetask(args, config, **kwargs)

        if subcommand != "run":
            # Unknown subcommand — fall back to local execution
            return run_pipetask(args, config, **kwargs)

        return self._submit_and_poll(args, config, **kwargs)

    def _submit_and_poll(
        self,
        args: list[str],
        config: Config,
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Submit a pipeline run to BPS and poll until completion."""
        parsed = _parse_pipetask_args(args)
        qgraph_file = parsed.get("qgraph_file")

        if not qgraph_file:
            log.warning("No qgraph file in args, falling back to local execution")
            return run_pipetask(args, config, **kwargs)

        # Build BPSConfig for submission
        output_run = parsed.get("output_run") or ""
        bps_cfg = bps.BPSConfig(
            pipeline="custom",  # Will use pre-built qgraph, not pipeline YAML
            night="00000000",  # Placeholder — qgraph has the actual data query
            site=self.site,
            container_image=self.container_image,
            qgraph_file=qgraph_file,
            output_run=output_run,
        )

        # Submit to BPS
        log.info(f"  Submitting to BPS (site={self.site}, qgraph={qgraph_file})")
        bps_result = bps.submit(bps_cfg, config)

        if not bps_result.success:
            log.error(f"  BPS submit failed: {bps_result.error}")
            return subprocess.CompletedProcess(
                args=["bps", "submit"],
                returncode=1,
                stdout="",
                stderr=bps_result.error or "BPS submission failed",
            )

        run_id = bps_result.run_id

        # Synchronous backend (Parsl): bps submit blocks until completion.
        # The job is already done when we get here. BPS exits 0 even when
        # all quanta fail (Parsl orchestration "succeeds"), so we check
        # Butler for the output_run collection as the definitive test.
        if not run_id:
            log.info("  BPS job completed (synchronous backend)")
            collection_exists = _check_output_collection(output_run, config)
            if collection_exists:
                log.info(f"  Output collection verified: {output_run}")
                returncode = 0
            else:
                log.warning(
                    f"  Output collection not found: {output_run} "
                    "(no quanta produced output)"
                )
                returncode = 1

            # Synthesize quanta summary for stage module parsing.
            # Use conservative counts: 1/0 based on collection existence.
            quanta_ok = 1 if collection_exists else 0
            quanta_fail = 0 if collection_exists else 1
            total = quanta_ok + quanta_fail

            result_stdout = (
                f"Executed {quanta_ok} quanta successfully, "
                f"{quanta_fail} failed out of total {total}"
            )
            return subprocess.CompletedProcess(
                args=["bps", "submit"],
                returncode=returncode,
                stdout=result_stdout,
                stderr=bps_result.stderr or "",
            )

        # Asynchronous backend (HTCondor): poll until completion
        log.info(f"  BPS job submitted: run_id={run_id}")

        interval = self.poll_interval
        max_interval = 60.0
        start = time.monotonic()

        while time.monotonic() - start < self.timeout:
            # Prefer the structured ctrl_bps Python API (state/counts keyed by
            # the WmsStates enum, immune to bps-report table formatting). Fall
            # back to parsing `bps report` stdout if it is unavailable.
            parsed_status = bps_report.summary_for_run(run_id, config)
            if parsed_status is None:
                raw_output = bps.status(run_id, config).get("output", "")
                parsed_status = _parse_bps_report(raw_output)
            state = parsed_status["state"]

            if state in ("SUCCEEDED", "FAILED", "DELETED"):
                log.info(
                    f"  BPS job {state}: {parsed_status['succeeded']} ok, "
                    f"{parsed_status['failed']} failed"
                )
                if bps_result.submit_dir:
                    log_file = kwargs.get("log_file")
                    if log_file:
                        with open(log_file, "a") as f:
                            f.write(
                                f"\nBPS job completed: run_id={run_id}, "
                                f"state={state}, "
                                f"logs at: {bps_result.submit_dir}/logging/\n"
                            )
                return _translate_bps_to_completed_process(parsed_status)

            time.sleep(interval)
            interval = min(interval * 1.5, max_interval)

        # Timeout
        log.warning(f"  BPS job timed out after {self.timeout}s (run_id={run_id})")
        return subprocess.CompletedProcess(
            args=["bps", "submit"],
            returncode=1,
            stdout="",
            stderr=f"BPS job timed out after {self.timeout}s (run_id={run_id})",
        )
