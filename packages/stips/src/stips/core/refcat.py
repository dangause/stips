"""On-demand Gaia/PS1 reference-catalog orchestration (no RSP/MONSTER).

``ensure_refcats`` is called from ``stips run`` before the science step. It is
idempotent: it computes the HTM7 trixels covering the target cone, checks which
are already present in the Butler ``refcats`` collection, and only fetches /
converts / ingests the missing ones.

No ``lsst.*`` import happens at module load — stack access is confined to
``run_with_stack`` / ``run_butler_query`` (mocked in unit tests).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from stips.core.stack import run_butler_query

if TYPE_CHECKING:
    from stips.core.config import Config


@dataclass
class RefcatResult:
    """Outcome of an ``ensure_refcats`` call."""

    mode: str
    gaia_status: str | None = None  # covered | fetched | skipped | failed
    ps1_status: str | None = None
    collections: list[str] = field(default_factory=list)
    needed_trixels: int = 0
    error: str | None = None


def _query_present_htm7(config: "Config", dataset_type: str) -> set[int]:
    """Return the htm7 ids already present for ``dataset_type`` in ``refcats``.

    Queries the Butler and parses htm7 dataId values out of the output. Isolated
    behind this function so unit tests can mock the Butler interaction.
    """
    repo = str(config.repo)
    result = run_butler_query(
        ["query-datasets", repo, "--collections", "refcats", dataset_type],
        config,
        check=False,
    )
    if getattr(result, "returncode", 1) != 0 or not getattr(result, "stdout", ""):
        return set()

    ids: set[int] = set()
    for line in result.stdout.splitlines():
        # htm7 appears as a bare integer dataId column in query-datasets output.
        for tok in re.findall(r"\b\d{3,}\b", line):
            ids.add(int(tok))
    return ids


def present_trixels(config: "Config", dataset_type: str) -> set[int]:
    """HTM7 trixels already covered for ``dataset_type``."""
    return _query_present_htm7(config, dataset_type)
