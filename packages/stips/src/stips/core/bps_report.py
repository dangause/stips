"""Structured BPS run status via the ctrl_bps Python API (replaces table scraping).

``executor._parse_bps_report`` reads the ``bps report <run_id>`` text table by
fixed column positions (``parts[1..7]``), which breaks whenever the table layout
changes — and it has: the v30 report table is rebuilt (per-task rows, exit-code
summaries) so the old ``summary``-row assumption no longer holds.

This adapter instead runs a small in-stack snippet that calls
``lsst.ctrl.bps.retrieve_report`` and reads ``WmsRunReport.state`` /
``.job_state_counts`` — counts keyed by the ``WmsStates`` *enum* (by identity,
never numeric value, since the values were re-numbered across releases), which is
immune to any text-table formatting. It emits a small JSON dict shaped exactly
like ``_parse_bps_report``'s output so it is a drop-in for the executor poll loop.

Scope / stability:
* Only the **async (HTCondor)** poll path uses this — the synchronous Parsl path
  verifies the Butler output collection instead (``ParslService.report`` raises
  ``NotImplementedError``). So the default service FQN here is HTCondor's.
* ctrl_bps is the least API-stable LSST surface; this is isolated in one module
  and callers fall back to ``_parse_bps_report`` when it returns ``None``, so the
  rarely-used BPS path never regresses. The live HTCondor path needs a running
  scheduler to exercise end-to-end (not available on dev boxes); the count
  mapping is validated against the real ``WmsRunReport``/``WmsStates`` types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stips.core.stack import run_butler_python_json

if TYPE_CHECKING:
    from stips.core.config import Config

#: The async backend whose runs are polled via ``retrieve_report``.
HTCONDOR_SERVICE = "lsst.ctrl.bps.htcondor.HTCondorService"


def _build_summary_script(run_id: str, wms_service_fqn: str) -> str:
    """In-stack snippet printing a ``_parse_bps_report``-shaped JSON dict.

    Prints ``{}`` (→ caller falls back) when no report is found or anything goes
    wrong; ``PRUNED`` jobs are folded into ``failed`` (they are downstream of a
    failure). State is the ``WmsStates`` member *name* (e.g. ``"SUCCEEDED"``),
    matching what the executor compares against.
    """
    return f"""
import json
try:
    from lsst.ctrl.bps import WmsStates
    from lsst.ctrl.bps.report import retrieve_report

    reports, _msgs = retrieve_report({wms_service_fqn!r}, run_id={run_id!r})
    if not reports:
        print("{{}}")
    else:
        r = reports[0]
        c = r.job_state_counts or {{}}
        print(json.dumps({{
            "state": r.state.name if r.state is not None else "UNKNOWN",
            "expected": int(r.total_number_jobs or 0),
            "succeeded": int(c.get(WmsStates.SUCCEEDED, 0)),
            "failed": int(c.get(WmsStates.FAILED, 0)) + int(c.get(WmsStates.PRUNED, 0)),
            "unready": int(c.get(WmsStates.UNREADY, 0)),
            "ready": int(c.get(WmsStates.READY, 0)),
            "running": int(c.get(WmsStates.RUNNING, 0)),
        }}))
except Exception:
    print("{{}}")
"""


def summary_for_run(
    run_id: str,
    config: "Config",
    *,
    wms_service_fqn: str = HTCONDOR_SERVICE,
) -> dict | None:
    """Return a structured status dict for a BPS run, or ``None`` to fall back.

    The dict has the same keys as ``executor._parse_bps_report``'s output
    (``state``/``expected``/``succeeded``/``failed``/``unready``/``ready``/
    ``running``). Returns ``None`` when the in-stack query failed or found no
    report, so callers fall back to parsing ``bps report`` stdout.
    """
    result = run_butler_python_json(
        _build_summary_script(run_id, wms_service_fqn), config
    )
    if isinstance(result, dict) and result.get("state"):
        return result
    return None


def _build_list_runs_script(wms_service_fqn: str) -> str:
    """In-stack snippet printing a JSON list of recent WMS runs.

    Calls ``retrieve_report`` with ``run_id=None`` (the documented way to *list*
    rather than fetch a single run) and emits one identifying dict per
    ``WmsRunReport`` — ``wms_id`` (the run id), plus ``run``/``payload``/``path``
    used by the caller to match the just-submitted workflow. Prints ``[]`` (→
    caller falls back) on any failure or when the WMS has no listable runs (e.g.
    the Parsl backend, whose ``report`` is unimplemented, or no live scheduler).
    """
    return f"""
import json
try:
    from lsst.ctrl.bps.report import retrieve_report

    reports, _msgs = retrieve_report({wms_service_fqn!r}, run_id=None)
    out = []
    for r in reports or []:
        out.append({{
            "wms_id": str(r.wms_id) if r.wms_id is not None else None,
            "run": r.run,
            "payload": r.payload,
            "path": r.path,
        }})
    print(json.dumps(out))
except Exception:
    print("[]")
"""


def list_runs(
    config: "Config",
    *,
    wms_service_fqn: str = HTCONDOR_SERVICE,
) -> list[dict] | None:
    """List recent WMS runs via ``retrieve_report(run_id=None)``.

    Each entry carries ``wms_id``/``run``/``payload``/``path``. Returns ``None``
    when the in-stack query failed or returned nothing, so callers can fall back
    to their existing behavior rather than acting on an empty list.
    """
    result = run_butler_python_json(_build_list_runs_script(wms_service_fqn), config)
    if isinstance(result, list) and result:
        return result
    return None
