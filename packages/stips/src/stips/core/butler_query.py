"""Structured, version-robust Butler queries (Phase-1 brittleness fix).

This module replaces brittle parsing of ``butler query-*`` CLI *tabular stdout*
(``parse_butler_query_output`` / ``butler_query_has_results`` in
``stips.core.pipeline``) with small snippets that use the **Butler Python query
API** and emit JSON. The snippet executes inside the activated LSST stack via
``run_butler_python_json()``; STIPS itself keeps running in its own venv and
never imports ``lsst.*`` directly (the established pattern, see
``core/coadd.py``).

Why this is more reliable
-------------------------
The butler CLI table layout (column order, headers, separators, Astropy
rendering) is presentation-only and is **not a stable API** — Rubin treats it as
such and it has drifted across releases. Counting non-header text rows silently
miscounts when the format changes. The Butler Python API returns real objects;
we serialize exactly the fields we need as JSON, which *we* control.

Version handling (gated inside each snippet, newest-first with a fallback)
-------------------------------------------------------------------------
* ``butler.query_datasets`` / ``butler.collections.query`` — public & stable
  v28+ (the surface Rubin's own CLI now uses internally).
* ``butler.registry.queryDatasets`` / ``queryCollections`` — fallback for v27.
* ``QuantumGraph.loadUri`` + ``len(qg)`` — stable v27+; the structural empty-graph
  check that replaces the ``"QuantumGraph contains no quanta"`` stdout grep.

All public helpers return ``None`` (or the documented empty value) when the
in-stack snippet fails to run, so callers can distinguish "query failed" from
"zero results".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from stips.core.stack import run_butler_python_json

if TYPE_CHECKING:
    from pathlib import Path

    from stips.core.config import Config


def _as_collection_list(collections: str | Sequence[str]) -> list[str]:
    """Normalize a collection name or glob (or sequence thereof) to a list."""
    if isinstance(collections, str):
        return [collections]
    return list(collections)


# --------------------------------------------------------------------------- #
# Snippet builders (pure string functions — unit-testable without a stack)
# --------------------------------------------------------------------------- #
def _build_count_script(
    repo: str,
    dataset_type: str,
    collections: list[str],
    where: str,
    limit: int | None,
) -> str:
    """Build an in-stack snippet that prints ``{"count": N}`` for a dataset query.

    Prefers ``butler.query_datasets(..., explain=False)`` (v28+, returns ``[]``
    instead of raising on an empty result) and falls back to the legacy
    ``registry.queryDatasets`` on older stacks. An unregistered dataset type maps
    to a count of 0 rather than an error.
    """
    return f"""
import json
from lsst.daf.butler import Butler
try:
    from lsst.daf.butler import MissingDatasetTypeError
except Exception:  # pragma: no cover - older stacks lack the symbol
    class MissingDatasetTypeError(Exception):
        pass

butler = Butler.from_config({repo!r}, writeable=False)
dataset_type = {dataset_type!r}
collections = {collections!r}
where = {where!r}
try:
    try:
        refs = butler.query_datasets(
            dataset_type,
            collections=collections,
            find_first=False,
            where=where,
            limit={limit!r},
            explain=False,
        )
    except (AttributeError, TypeError, ValueError):
        # v27 fallback: no butler.query_datasets / no limit kwarg
        refs = list(butler.registry.queryDatasets(
            dataset_type, collections=collections, where=where))
    print(json.dumps({{"count": len(list(refs))}}))
except MissingDatasetTypeError:
    print(json.dumps({{"count": 0}}))
"""


def _build_list_collections_script(repo: str, pattern: str) -> str:
    """Build an in-stack snippet that prints ``{"collections": [...]}`` for a glob."""
    return f"""
import json
from lsst.daf.butler import Butler

butler = Butler.from_config({repo!r}, writeable=False)
pattern = {pattern!r}
try:
    names = list(butler.collections.query(pattern))
except AttributeError:
    # v27 fallback
    names = list(butler.registry.queryCollections(pattern))
print(json.dumps({{"collections": sorted(names)}}))
"""


def _build_qg_count_script(qg_path: str) -> str:
    """Build an in-stack snippet that prints ``{"count": N}`` for a saved qgraph.

    ``len(qg)`` is the documented count of quanta (QuantumNodes); there is no
    ``isEmpty()``/``numberOfQuanta()``. Loading the file STIPS itself just wrote
    avoids any on-disk version skew.
    """
    return f"""
import json
from lsst.pipe.base import QuantumGraph

qg = QuantumGraph.loadUri({qg_path!r})
print(json.dumps({{"count": len(qg)}}))
"""


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def count_datasets(
    config: "Config",
    dataset_type: str,
    collections: str | Sequence[str],
    *,
    where: str = "",
) -> int | None:
    """Count datasets of ``dataset_type`` in ``collections``.

    Returns the integer count, or ``None`` if the in-stack query failed to run.
    Replaces ``len(parse_butler_query_output(result.stdout))``.
    """
    script = _build_count_script(
        str(config.repo), dataset_type, _as_collection_list(collections), where, None
    )
    result = run_butler_python_json(script, config)
    if isinstance(result, dict) and "count" in result:
        return int(result["count"])
    return None


def has_datasets(
    config: "Config",
    dataset_type: str,
    collections: str | Sequence[str],
    *,
    where: str = "",
) -> bool:
    """Return True iff at least one matching dataset exists (``limit=1`` query).

    Replaces ``butler_query_has_results(result.stdout)``. A failed query reads as
    False (matching the old "no rows parsed" behavior).
    """
    script = _build_count_script(
        str(config.repo), dataset_type, _as_collection_list(collections), where, 1
    )
    result = run_butler_python_json(script, config)
    if isinstance(result, dict) and "count" in result:
        return int(result["count"]) > 0
    return False


def list_collections(
    config: "Config",
    pattern: str,
    *,
    prefix: str | None = None,
) -> list[str] | None:
    """List collection names matching ``pattern`` (glob), optionally prefix-filtered.

    Returns the sorted names, or ``None`` if the in-stack query failed to run.
    Replaces ``parse_butler_query_output(result.stdout, prefix_filter=...)``.
    """
    script = _build_list_collections_script(str(config.repo), pattern)
    result = run_butler_python_json(script, config)
    if isinstance(result, dict) and "collections" in result:
        names = [str(n) for n in result["collections"]]
        if prefix is not None:
            names = [n for n in names if n.startswith(prefix)]
        return names
    return None


def collection_exists(config: "Config", name: str) -> bool:
    """Return True iff a collection named ``name`` exists.

    A failed query reads as False (matching the old behavior of a missing row).
    """
    names = list_collections(config, name)
    return bool(names) and name in names


def quantum_graph_quanta_count(config: "Config", qg_path: "Path | str") -> int | None:
    """Return the number of quanta in a saved ``.qgraph`` file, or ``None`` on failure."""
    script = _build_qg_count_script(str(qg_path))
    result = run_butler_python_json(script, config)
    if isinstance(result, dict) and "count" in result:
        return int(result["count"])
    return None


def quantum_graph_is_empty(config: "Config", qg_path: "Path | str") -> bool | None:
    """Return True if the saved qgraph has zero quanta, False if >0, ``None`` on failure.

    Structural replacement for ``is_empty_qgraph(stdout)`` — it inspects the graph
    object instead of grepping the human-readable log line
    ``"QuantumGraph contains no quanta"``.
    """
    count = quantum_graph_quanta_count(config, qg_path)
    if count is None:
        return None
    return count == 0
