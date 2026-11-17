"""BPS quantum clustering: how a submitted graph is split into jobs.

Every job BPS runs starts a fresh ``pipetask run-qbb`` process, about 10 s of
imports (25 s on a busy shared filesystem) before any work, while most STIPS
quanta then run for under 5 s; within a job, quanta run one after another in
that one process. Two algorithms, chosen with ``options.cluster.clustering``:

- :func:`grouped_clustering` (``grouped``, the default): a graph's per-visit
  tasks run as at most as many jobs as a block runs at once, each taking a
  share of the visits, and the tasks that combine visits run as one job.
- :func:`visit_clustering` (``visit``): one job per visit (two, see
  :func:`visit_cluster_config`); every task that combines visits is a job of
  its own.

Both hand ``ctrl_bps``'s ``dimension_clustering`` a cluster definition. A
failed quantum does not stop the others in its job, and a retried job skips
the quanta that already finished (``run-qbb`` runs with ``skip_existing``).

Only the task selection is here without the stack, so it can be tested in a
plain virtualenv.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = (
    "MAX_JOBS_KEY",
    "grouped_cluster_config",
    "grouped_clustering",
    "visit_cluster_config",
    "visit_clustering",
    "visit_task_labels",
)

#: BPS config key (set by the site file) giving how many jobs a cluster of
#: per-visit tasks may be split into: the quanta one block runs at once.
MAX_JOBS_KEY = "stipsMaxJobsPerCluster"

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
    return _visit_groups(order, dims, preds)[0]


def _visit_groups(
    order: Iterable[str],
    dims: Mapping[str, Iterable[str]],
    preds: Mapping[str, Iterable[str]],
) -> tuple[list[str], list[str]]:
    """Per-visit tasks (see :func:`visit_task_labels`), and the tasks downstream of them.

    Returns ``(members, downstream)``, both in dependency order.
    """
    order = list(order)
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
    return members, [label for label in order if label in depends_on_group]


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
    core, leaves = _core_and_leaves(order, labels, preds)

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



def _core_and_leaves(
    order: list[str], members: list[str], preds: Mapping[str, Iterable[str]]
) -> tuple[list[str], list[str]]:
    """Split per-visit tasks into those something outside needs, and the rest.

    Members with a descendant outside the group are found walking backwards
    from the tasks outside it.
    """
    member_set = set(members)
    needed: set[str] = set()
    feeds_outside = {label for label in order if label not in member_set}
    for label in reversed(order):
        if label in feeds_outside or label in needed:
            needed.update(p for p in preds.get(label, ()) if p in member_set)
    return (
        [label for label in members if label in needed],
        [label for label in members if label not in needed],
    )


def grouped_cluster_config(
    order: Iterable[str],
    dims: Mapping[str, Iterable[str]],
    preds: Mapping[str, Iterable[str]],
    max_jobs: int,
) -> dict[str, dict[str, Any]] | None:
    """Return the BPS ``cluster`` section for :func:`grouped_clustering`, or ``None``.

    - ``visit``: the per-visit tasks something later needs, split by visit
      into at most ``max_jobs`` jobs.
    - ``visit_leaves``: the other per-visit tasks (analysis, plots), split
      the same way. BPS skips every job downstream of a failed one, so a
      failing leaf must not share a job with what later tasks need.
    - ``combine``: every task downstream of the per-visit tasks, one job.

    ``None`` when the graph has no per-visit task.
    """
    order = list(order)
    members, downstream = _visit_groups(order, dims, preds)
    if not members:
        return None
    core, leaves = _core_and_leaves(order, members, preds)

    def split(tasks: list[str]) -> dict[str, Any]:
        return {
            "pipetasks": ", ".join(tasks),
            "partitionDimensions": "visit",
            "equalDimensions": "visit:exposure",
            "partitionMaxClusters": max(1, int(max_jobs)),
        }

    section: dict[str, dict[str, Any]] = {}
    if core:
        section["visit"] = split(core)
    if leaves:
        section["visit_leaves" if core else "visit"] = split(leaves)
    if downstream:
        section["combine"] = {"pipetasks": ", ".join(downstream)}
    return section


def grouped_clustering(config: Any, qgraph: Any, name: str) -> Any:
    """``clusterAlgorithm`` for BPS: few jobs per graph (see :func:`grouped_cluster_config`).

    A STIPS graph is one night of one band group, so per-visit jobs mostly
    paid ``pipetask`` start-up, and each task combining visits added a job
    that waited on the one before. Falls back to :func:`visit_clustering` if
    ``ctrl_bps`` rejects the grouping. A non-empty ``cluster`` section in the
    BPS config is used as written.
    """
    from lsst.ctrl.bps.quantum_clustering_funcs import dimension_clustering
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
    found, max_jobs = config.search(MAX_JOBS_KEY)
    section = grouped_cluster_config(order, dims, preds, int(max_jobs) if found else 1)
    if section is None:
        return visit_clustering(config, qgraph, name)
    config["cluster"] = section
    try:
        return dimension_clustering(config, qgraph, name)
    except RuntimeError:
        config["cluster"] = {}
        return visit_clustering(config, qgraph, name)
