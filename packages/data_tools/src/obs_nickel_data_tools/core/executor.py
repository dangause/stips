"""Execution backends for pipetask commands.

Provides an abstraction over how pipetask commands are executed, allowing
the same stage module code to run via direct subprocess (LocalExecutor)
or via BPS batch submission (BPSExecutor).

Stage modules call executor.run_pipetask() instead of stack.run_pipetask(),
preserving all existing stage-level logic (fallbacks, validation, etc.).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from obs_nickel_data_tools.core.stack import run_pipetask

if TYPE_CHECKING:

    from obs_nickel_data_tools.core.config import Config


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
