"""In-stack validation of every shipped pipeline YAML against the installed stack.

STIPS ships ~a dozen pipeline YAMLs under
``packages/obs_stips/instrument_defaults/pipelines/``. Each embeds ``class:``
task FQNs (e.g. ``lsst.pipe.tasks.calibrateImage.CalibrateImageTask``) and dozens
of config-field overrides (``qMin``/``qMax``, ``maxPsfFwhm``, ``maxEllipResidual``,
connection renames, ...). These names are coupled to the installed LSST stack and
have broken across stack versions before. Historically only the ``#coadds-only``
subset of ``DRP.yaml`` had an in-stack config test
(``instruments/nickel/tests/test_drp_pipeline_config.py``); everything else was
validated only at runtime on real data, serially, after a stack bump.

This module closes that gap. It builds a task graph for:

* every ``.yaml`` under the pipelines dir (``test_pipeline_builds_task_graph``),
  discovered by glob so new pipelines are covered with no test edit; and
* every ``<yaml>#<label>`` subset that STIPS actually invokes at runtime
  (``test_invoked_subset_builds_task_graph``), so a subset label that stops
  resolving fails here rather than mid-pipeline.

``Pipeline.to_graph()`` imports every task class and applies/validates every
config override *without needing a Butler repo or data* -- it resolves the task
graph, not a quantum graph. Where STIPS injects config at runtime (e.g.
``--config-file calibrateImage:apply_colorterms.py`` in ``science.py``, or
``differentialPhot`` target coords in ``run.py``), the test injects the same
config so the graph is validated exactly as STIPS runs it (see
``_apply_stips_runtime_config``).

Some pipelines cannot build their *full default* graph on this stack for reasons
outside STIPS's control (upstream ``analysis_tools`` breakage; drp_pipe generic
ingredients that need an instrument-provided colorterms library STIPS does not
supply). Those are marked ``xfail`` per-pipeline with a reason -- but the tasks
STIPS actually runs from them are still covered by the subset test, which passes.
See ``_XFAIL_DEFAULT_GRAPH``.

Skips cleanly in a plain venv via ``pytest.importorskip`` (no ``lsst.pipe.base``).
Requires the LSST stack; run under ``scripts/with-stack.sh`` (which also sets up
``obs_stips`` and ``INSTRUMENT_DIR``). This test lives in ``obs_stips`` because
``obs_stips`` is the package that *ships* these pipelines, and it discovers them
relative to its own location -- no env var needed to find them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# packages/obs_stips/tests/test_pipeline_graphs.py
#   parents[1] == packages/obs_stips
#   parents[3] == repo root
_OBS_STIPS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]

PIPELINES_DIR = _OBS_STIPS_DIR / "instrument_defaults" / "pipelines"
# ``$STIPS_DEFAULTS`` is the framework-defaults root that pipelines ``import`` via
# ``$STIPS_DEFAULTS/pipelines/...``. run_with_stack exports it at runtime; set it
# file-relative here (matching test_drp_pipeline_config.py) to stay self-contained.
STIPS_DEFAULTS_ROOT = _OBS_STIPS_DIR / "instrument_defaults"
# calibrateImage's colorterm library is injected by STIPS at runtime via
# ``--config-file calibrateImage:<this file>`` (science.py); the DRP.yaml itself
# only sets ``photometry.applyColorTerms: true`` and leaves the library empty.
APPLY_COLORTERMS_PATH = STIPS_DEFAULTS_ROOT / "configs" / "apply_colorterms.py"
# Instrument-bearing pipelines (ForcedPhotRaDec.yaml declares
# ``instrument: lsst.obs.stips.active.Instrument``) synthesize the instrument from
# INSTRUMENT_DIR when the graph is built. with-stack.sh exports it, but pin it to
# the reference Nickel instrument so this test is self-contained.
INSTRUMENT_DIR_PATH = _REPO_ROOT / "instruments" / "nickel"

# Discovered dynamically so new pipelines are validated with no test edit.
ALL_PIPELINES = sorted(PIPELINES_DIR.glob("*.yaml"))

# The exact ``<yaml>#<label>`` subsets STIPS invokes at runtime, grepped from
# packages/stips/src/stips/core/{science,coadd,dia,fphot}.py. A label that no
# longer resolves is a real break (the CLI would fail), so it must fail here.
#   science.py:498  DRP.yaml#stage1-single-visit
#   science.py:834  DRP.yaml#coadds-only
#   coadd.py:444    DRP.yaml#coadds-only
#   dia.py:281      DIA.yaml#dia-full
#   fphot.py:190    ForcedPhotRaDec.yaml#visit-image
#   fphot.py:263    ForcedPhotRaDec.yaml#diffim
# Whole-file invocations (calibs.py CpBias/CpFlat, run.py DifferentialPhot) need
# no subset entry -- they are covered by the default-graph test above.
INVOKED_SUBSETS = [
    ("DRP.yaml", "stage1-single-visit"),
    ("DRP.yaml", "coadds-only"),
    ("DIA.yaml", "dia-full"),
    ("ForcedPhotRaDec.yaml", "visit-image"),
    ("ForcedPhotRaDec.yaml", "diffim"),
]

# Pipelines whose FULL default graph cannot build on the installed stack for
# reasons outside STIPS's control. The tasks STIPS actually runs from these
# pipelines are covered by test_invoked_subset_builds_task_graph, which passes.
# xfail is non-strict on purpose: if a future stack fixes the upstream issue the
# test XPASSes (a signal to delete the entry) without turning the canary red.
_XFAIL_DEFAULT_GRAPH = {
    "DRP.yaml": (
        "Full DRP default graph pulls in drp_pipe's generic (non-Nickel) "
        "analysis ingredients: makeAnalysisSingleVisitStarPhotometricRefMatch "
        "needs an instrument-provided colorterms library STIPS does not supply, "
        "and analyzeDiaSources' analysis_tools SimpleDiaPlot is broken upstream "
        "(setDefaults sets removed DiaSkyPanel.ra). STIPS never runs the full "
        "DRP graph; the subsets it runs (stage1-single-visit, coadds-only) are "
        "covered by test_invoked_subset_builds_task_graph."
    ),
    "DIA.yaml": (
        "analyzeDiaSources uses analysis_tools SimpleDiaPlot, whose setDefaults() "
        "sets a removed DiaSkyPanel.ra field in the installed stack (upstream "
        "break). STIPS invokes DIA.yaml#dia-full, which omits the QA plot task "
        "and is covered/passing in test_invoked_subset_builds_task_graph."
    ),
    "analysis-dia-detector.yaml": (
        "analyzeDiaSources uses analysis_tools SimpleDiaPlot, whose setDefaults() "
        "sets a removed DiaSkyPanel.ra field in the installed stack (upstream "
        "break). This ingredient is imported by DIA.yaml/DRP.yaml but never run "
        "standalone by STIPS."
    ),
}


def _pipeline_param(path: Path):
    """Wrap a pipeline path in a pytest.param, attaching xfail where known."""
    reason = _XFAIL_DEFAULT_GRAPH.get(path.name)
    marks = (pytest.mark.xfail(reason=reason, strict=False),) if reason else ()
    return pytest.param(path, id=path.name, marks=marks)


def _prime_env(monkeypatch) -> None:
    """Export the env vars the pipeline YAMLs interpolate at load time.

    Other stack-package roots ($DRP_PIPE_DIR, $CP_PIPE_DIR, $PIPE_TASKS_DIR,
    $ANALYSIS_TOOLS_DIR) are set by ``setup lsst_distrib`` in with-stack.sh; only
    the two STIPS-specific vars below are not, so we set them here.
    """
    monkeypatch.setenv("STIPS_DEFAULTS", str(STIPS_DEFAULTS_ROOT))
    monkeypatch.setenv("INSTRUMENT_DIR", str(INSTRUMENT_DIR_PATH))


def _apply_stips_runtime_config(pipeline, yaml_name: str) -> None:
    """Inject the config STIPS applies at runtime, so the graph builds as it runs.

    The pipeline YAMLs intentionally leave some fields to be filled at runtime by
    the CLI (colorterm libraries, target coordinates). Mirror those injections so
    ``to_graph`` validates the exact configuration STIPS executes -- rather than
    failing on a placeholder the CLI always overrides. Guards on task membership
    so it is a no-op for subsets that exclude the task.
    """
    labels = pipeline.task_labels
    if yaml_name == "DRP.yaml" and "calibrateImage" in labels:
        # science.py: --config-file calibrateImage:apply_colorterms.py
        pipeline.addConfigFile("calibrateImage", str(APPLY_COLORTERMS_PATH))
    if yaml_name == "DifferentialPhot.yaml" and "differentialPhot" in labels:
        # run.py: -c differentialPhot:targetRa/targetDec (target coords). Values
        # are arbitrary non-zero coords -- the task requires them to be set.
        pipeline.addConfigOverride("differentialPhot", "targetRa", 210.910750)
        pipeline.addConfigOverride("differentialPhot", "targetDec", 54.311694)


@pytest.mark.parametrize(
    "pipeline_path",
    [_pipeline_param(p) for p in ALL_PIPELINES],
)
def test_pipeline_builds_task_graph(pipeline_path: Path, monkeypatch) -> None:
    """Every shipped pipeline YAML builds a task graph against the installed stack.

    ``to_graph()`` instantiates each task and validates each config override; it
    does NOT need a repo or data (it resolves the task graph, not quanta). If a
    task FQN or config field drifted out from under the YAML, this raises.
    """
    lsst_pipe_base = pytest.importorskip("lsst.pipe.base")
    _prime_env(monkeypatch)

    pipeline = lsst_pipe_base.Pipeline.fromFile(str(pipeline_path))
    _apply_stips_runtime_config(pipeline, pipeline_path.name)
    graph = pipeline.to_graph()
    assert len(graph.tasks) > 0, f"{pipeline_path.name} produced an empty task graph"


@pytest.mark.parametrize(
    "yaml_name,subset",
    INVOKED_SUBSETS,
    ids=[f"{name}#{subset}" for name, subset in INVOKED_SUBSETS],
)
def test_invoked_subset_builds_task_graph(
    yaml_name: str, subset: str, monkeypatch
) -> None:
    """Each ``#<label>`` subset STIPS invokes still resolves and builds a graph."""
    lsst_pipe_base = pytest.importorskip("lsst.pipe.base")
    _prime_env(monkeypatch)

    path = PIPELINES_DIR / yaml_name
    pipeline = lsst_pipe_base.Pipeline.fromFile(f"{path}#{subset}")
    _apply_stips_runtime_config(pipeline, yaml_name)
    graph = pipeline.to_graph()
    assert len(graph.tasks) > 0, f"{yaml_name}#{subset} produced an empty task graph"
