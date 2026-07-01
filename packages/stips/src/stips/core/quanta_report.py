"""Structured quanta success/failure counts from ``pipetask run --summary``.

Replaces ``parse_quanta_summary()``'s regex over the human-readable
``"Executed N quanta successfully, M failed and K remain"`` log line with the
machine-readable JSON that ``pipetask run --summary <file>`` writes (a
``lsst.pipe.base.quantum_reports.Report`` serialized via pydantic).

The serialized report has a top-level ``"quantaReports"`` list whose items each
carry a lowercase ``"status"`` (``"success"`` / ``"failure"`` / ``"timeout"`` /
``"skipped"``, confirmed against the installed v30 stack). We parse it with the
standard-library ``json`` in the venv — no ``lsst`` import and no extra
subprocess — and never touch the human-readable stdout.

Stability note: Rubin documents the ``--summary`` JSON structure as one that
"may not be stable", so this is the *preferred* signal with
``stips.core.pipeline.parse_quanta_summary`` kept as a fallback (callers treat a
``None`` return here as "fall back to the regex"). The parser is intentionally
defensive: any shape it does not recognize yields ``None`` rather than a wrong
count.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

#: status string (lowercase) that counts as a successfully-executed quantum
_SUCCESS = "success"
#: statuses that count as a failed quantum (skipped/unknown are counted as neither,
#: matching the "executed successfully / failed" semantics of the old regex)
_FAIL = frozenset({"failure", "timeout"})


def summary_run_args(path: "Path | str") -> list[str]:
    """``pipetask run`` args that write a machine-readable summary to ``path``."""
    return ["--summary", str(path)]


def parse_summary_file(path: "Path | str") -> tuple[int, int] | None:
    """Return ``(succeeded, failed)`` from a ``pipetask run --summary`` JSON file.

    Returns ``None`` when the file is missing, unreadable, or has no recognizable
    ``quantaReports`` list, so callers can fall back to the stdout/log regex in
    ``parse_quanta_summary``.
    """
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    quanta = data.get("quantaReports") if isinstance(data, dict) else None
    if not isinstance(quanta, list):
        return None

    succeeded = failed = 0
    for q in quanta:
        if not isinstance(q, dict):
            continue
        status = str(q.get("status", "")).lower()
        if status == _SUCCESS:
            succeeded += 1
        elif status in _FAIL:
            failed += 1
    return succeeded, failed
