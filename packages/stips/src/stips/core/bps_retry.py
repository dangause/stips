"""Which failed BPS jobs Parsl runs again.

Parsl retries every failed task up to ``retries`` times. A job whose
``pipetask`` exited non-zero has a quantum that failed for its own reasons
(no astrometric match, too few stars): run again it fails the same way, and
STIPS's fallback configs exist for exactly those quanta. Running it again
only delays the step. A job that failed because its worker or node went away
did not run at all, and is worth retrying.

Kept free of Parsl and the stack so it can be tested in a plain virtualenv.
"""

from __future__ import annotations

from typing import Any

__all__ = ("retry_cost",)

#: Parsl's exception for a bash app that exited with a non-zero status.
_EXIT_FAILURE = "BashExitFailure"


def retry_cost(exc: BaseException, task_record: Any, *, retries: int) -> float:
    """Parsl ``retry_handler``: the cost a failure adds toward ``retries``.

    Parsl retries a task while its accumulated cost is at most ``retries``,
    so a cost above it ends the task.
    """
    if any(cls.__name__ == _EXIT_FAILURE for cls in type(exc).__mro__):
        return float(retries + 1)
    return 1.0
