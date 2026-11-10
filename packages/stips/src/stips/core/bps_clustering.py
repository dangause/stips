"""BPS quantum clustering: one job per visit.

Every quantum BPS runs as its own job starts a fresh ``pipetask run-qbb``
process, about 10 s of imports before any work, while most per-visit tasks
then run for under 5 s. Grouping a visit's quanta into one job pays that cost
once per visit instead of once per quantum.

The site file names :func:`visit_clustering` as ``clusterAlgorithm``. It
runs inside ``bps submit``, works out which tasks of the submitted graph can
share a visit's job (two jobs per visit; see :func:`visit_cluster_config`),
and hands ``ctrl_bps``'s ``dimension_clustering`` the cluster definition. A failed quantum does not stop the others in its job, and
a retried job skips the quanta that already finished (``run-qbb`` runs with
``skip_existing``).

Only the task selection is here without the stack, so it can be tested in a
plain virtualenv.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ("visit_cluster_config", "visit_clustering", "visit_task_labels")

#: Dimensions that place a quantum in one visit. ``exposure`` counts as
#: ``visit`` (``isr`` runs per exposure), which needs one exposure per visit,
#: as every STIPS instrument has.
_VISIT_DIMENSIONS = ("visit", "exposure")


def visit_task_labels(
    order: Iterable[str],
    dims: Mapping[str, Iterable[str]],
    preds: Mapping[str, Iterable[str]],
) -> list[str]:
    """Return the tasks that can run in one job per visit.

    A task joins when it has a visit (or exposure) dimension, unless one of
    its inputs comes from a task outside the group that itself depends on the
    group: the visit's job would then wait on a job that waits on it.

    Args:
        order: Task labels, in dependency order.
        dims: Each task's dimension names.
        preds: Each task's upstream task labels.
    """
    members: list[str] = []
    in_group: set[str] = set()
    depends_on_group: set[str] = set()
    for label in order:
        upstream = set(preds.get(label, ()))
        per_visit = any(d in set(dims.get(label, ())) for d in _VISIT_DIMENSIONS)
        blocked = any(p not in in_group and p in depends_on_group for p in upstream)
        if per_visit and not blocked:
            members.append(label)
            in_group.add(label)
        elif upstream & (in_group | depends_on_group):
            depends_on_group.add(label)
    return members


def visit_cluster_config(
    order: Iterable[str],
    dims: Mapping[str, Iterable[str]],
    preds: Mapping[str, Iterable[str]],
) -> dict[str, dict[str, str]] | None:
    """Return the BPS ``cluster`` section for per-visit jobs, or ``None``.

    BPS skips every job downstream of a failed one, even where the failed
    quantum's outputs are not needed, so the per-visit tasks split in two:
    ``visit`` holds those that some task outside the visit depends on, and
    ``visit_leaves`` the rest (analysis and plots, typically), so that a
    failing leaf quantum does not hold back the tasks that combine visits.
    With nothing outside depending on the visit, its tasks are one
    ``visit`` cluster.

    ``None`` when fewer than two tasks would be grouped, where grouping gains
    nothing.
    """
    order = list(order)
    labels = visit_task_labels(order, dims, preds)
    if len(labels) < 2:
        return None
    members = set(labels)
    # Members with a descendant outside the group, found walking backwards
    # from the tasks outside it.
    needed: set[str] = set()
    feeds_outside = {label for label in order if label not in members}
    for label in reversed(order):
        if label in feeds_outside or label in needed:
            needed.update(p for p in preds.get(label, ()) if p in members)
    core = [label for label in labels if label in needed]
    leaves = [label for label in labels if label not in needed]

    def cluster(tasks: list[str]) -> dict[str, str]:
        return {
            "pipetasks": ", ".join(tasks),
            "dimensions": "visit",
            "equalDimensions": "visit:exposure",
        }

    if not core:
        return {"visit": cluster(leaves)}
    section = {"visit": cluster(core)}
    if leaves:
        section["visit_leaves"] = cluster(leaves)
    return section


def _defines_clusters(config: Any) -> bool:
    """Whether the BPS config defines clusters itself.

    The submitted config carries an empty ``cluster`` section by default,
    which defines none.
    """
    found, section = config.search("cluster")
    return bool(found and section)


def visit_clustering(config: Any, qgraph: Any, name: str) -> Any:
    """``clusterAlgorithm`` for BPS: one job per visit.

    A non-empty ``cluster`` section in the BPS config is used as written.
    """
    from lsst.ctrl.bps.quantum_clustering_funcs import (
        dimension_clustering,
        single_quantum_clustering,
    )
    from networkx import topological_sort

    if _defines_clusters(config):
        return dimension_clustering(config, qgraph, name)

    pipeline_graph = qgraph.pipeline_graph
    xgraph = pipeline_graph.make_task_xgraph()
    order = [key.name for key in topological_sort(xgraph)]
    preds = {key.name: {p.name for p in xgraph.predecessors(key)} for key in xgraph}
    dims = {
        label: set(pipeline_graph.tasks[label].dimensions.names) for label in order
    }
    section = visit_cluster_config(order, dims, preds)
    if section is None:
        return single_quantum_clustering(config, qgraph, name)
    config["cluster"] = section
    return dimension_clustering(config, qgraph, name)
