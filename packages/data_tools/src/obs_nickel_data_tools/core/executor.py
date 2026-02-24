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
