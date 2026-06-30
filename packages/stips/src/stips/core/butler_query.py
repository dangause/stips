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

from typing import TYPE_CHECKING, Any, Sequence

from stips.core.stack import run_butler_python_json

if TYPE_CHECKING:
    from pathlib import Path

    from stips.core.config import Config


def _as_collection_list(collections: str | Sequence[str]) -> list[str]:
    """Normalize a collection name or glob (or sequence thereof) to a list."""
    if isinstance(collections, str):
        return [collections]
    return list(collections)


def _field(result: Any, key: str) -> Any | None:
    """Pull ``key`` out of a snippet's JSON-dict result, or ``None``.

    Returns ``None`` when the snippet failed (``result`` is not a dict) or the
    key is absent — the single shape every public helper below keys off.
    """
    return result.get(key) if isinstance(result, dict) else None


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
        # v27 fallback: registry.queryDatasets has no limit kwarg, so apply the
        # cap manually — otherwise an existence check (limit=1) full-scans.
        import itertools
        _q = butler.registry.queryDatasets(
            dataset_type, collections=collections, where=where)
        _lim = {limit!r}
        refs = list(_q if _lim is None else itertools.islice(_q, _lim))
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


def _build_collection_types_script(repo: str, pattern: str) -> str:
    """Build a snippet printing ``{"collections": {name: TYPE}}`` for a glob.

    Uses ``butler.collections.query_info`` (v28+) so the collection *type*
    (RUN/CHAINED/CALIBRATION/...) comes from a typed ``CollectionInfo`` rather
    than the last whitespace column of the CLI table.
    """
    return f"""
import json
from lsst.daf.butler import Butler

butler = Butler.from_config({repo!r}, writeable=False)
pattern = {pattern!r}
try:
    infos = butler.collections.query_info(pattern)
    out = {{ci.name: ci.type.name for ci in infos}}
except AttributeError:
    # v27 fallback
    names = list(butler.registry.queryCollections(pattern))
    out = {{n: butler.registry.getCollectionType(n).name for n in names}}
print(json.dumps({{"collections": out}}))
"""


def _build_collection_has_datasets_script(repo: str, name: str) -> str:
    """Build a snippet printing ``{"has_datasets": bool}`` for one collection.

    True iff the collection exists *and* its dataset-type summary is non-empty.
    A missing collection or an empty RUN both read as False — exactly the
    "does this RUN actually contain output?" check BPS needs (an empty RUN
    shell created before quanta run has no dataset types).
    """
    return f"""
import json
from lsst.daf.butler import Butler

butler = Butler.from_config({repo!r}, writeable=False)
try:
    info = butler.collections.get_info({name!r}, include_summary=True)
    has = bool(getattr(info, "dataset_types", None))
except Exception:
    has = False
print(json.dumps({{"has_datasets": has}}))
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
    count = _field(run_butler_python_json(script, config), "count")
    return int(count) if count is not None else None


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
    count = _field(run_butler_python_json(script, config), "count")
    return count is not None and int(count) > 0


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
    raw = _field(run_butler_python_json(script, config), "collections")
    if raw is None:
        return None
    names = [str(n) for n in raw]
    if prefix is not None:
        names = [n for n in names if n.startswith(prefix)]
    return names


def collection_exists(config: "Config", name: str) -> bool:
    """Return True iff a collection named ``name`` exists.

    A failed query reads as False (matching the old behavior of a missing row).
    """
    names = list_collections(config, name)
    return bool(names) and name in names


def list_collection_types(config: "Config", pattern: str) -> dict[str, str] | None:
    """Map matching collection names to their type (RUN/CHAINED/CALIBRATION/...).

    Returns ``None`` if the in-stack query failed. Replaces parsing the type out
    of the last whitespace column of ``butler query-collections`` output.
    """
    script = _build_collection_types_script(str(config.repo), pattern)
    cols = _field(run_butler_python_json(script, config), "collections")
    if not isinstance(cols, dict):
        return None
    return {str(k): str(v) for k, v in cols.items()}


def collection_has_datasets(config: "Config", name: str) -> bool:
    """Return True iff ``name`` exists *and* holds at least one dataset.

    Uses the collection's dataset-type summary, so an empty RUN shell (created by
    BPS before quanta run) reads as False. A failed query reads as False.
    """
    script = _build_collection_has_datasets_script(str(config.repo), name)
    return bool(_field(run_butler_python_json(script, config), "has_datasets"))


def quantum_graph_quanta_count(config: "Config", qg_path: "Path | str") -> int | None:
    """Return the number of quanta in a saved ``.qgraph`` file, or ``None`` on failure."""
    script = _build_qg_count_script(str(qg_path))
    count = _field(run_butler_python_json(script, config), "count")
    return int(count) if count is not None else None


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
