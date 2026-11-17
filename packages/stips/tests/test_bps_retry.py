"""Parsl does not run a job again when its pipetask exited non-zero."""

from __future__ import annotations

from stips.core.bps_retry import retry_cost


class BashExitFailure(Exception):
    """Stand-in with the name of Parsl's exception (parsl.app.errors)."""


class SubclassedExit(BashExitFailure):
    pass


class ManagerLost(Exception):
    pass


def test_pipetask_exit_failure_is_not_retried():
    # Parsl retries while the accumulated cost is <= retries.
    assert retry_cost(BashExitFailure(), {}, retries=1) > 1
    assert retry_cost(SubclassedExit(), {}, retries=3) > 3


def test_lost_worker_is_retried():
    assert retry_cost(ManagerLost(), {}, retries=1) == 1.0
