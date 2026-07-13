"""BPS (Batch Processing Service) integration for Small Telescope Image Processing Suite.

This module provides functionality for submitting pipelines to HPC clusters
using LSST's BPS (Batch Processing Service) with Parsl or HTCondor backends.

Example usage:
    from stips.core.bps import BPSConfig, submit

    bps_cfg = BPSConfig(
        pipeline="science",
        night="20230519",
        site="slurm",
    )
    result = submit(bps_cfg, config)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from stips.collections import template_ps1
from stips.core.config import resolve_data_package_dir
from stips.core.query import butler_str_literal

if TYPE_CHECKING:
    from stips.core.config import Config


log = logging.getLogger(__name__)


# Repo's packages/ directory (bps.py is at packages/stips/src/stips/core/bps.py;
# parents[4] == packages/). Used to locate sibling framework packages
# (obs_stips, stips) and the instrument data package for BPS preScript setup.
_PACKAGES_DIR = Path(__file__).resolve().parents[4]


# Valid pipeline names
VALID_PIPELINES = ("calibs", "science", "dia", "fphot", "custom")

# Valid site names
VALID_SITES = ("slurm", "htcondor", "local", "singularity-slurm", "docker-slurm")

# Sites whose ``wmsServiceClass`` is Parsl (see ``bps/sites/*.yaml``). Parsl runs
# *synchronously* — ``bps submit`` blocks until the workflow finishes and there is
# no pollable WMS run (``ParslService.report`` raises ``NotImplementedError``), so
# a missing run id on these sites is EXPECTED, not an error. HTCondor is the only
# asynchronous site: it submits and returns a run id for later polling.
_PARSL_SITES = frozenset({"local", "slurm", "singularity-slurm", "docker-slurm"})
_HTCONDOR_SITES = frozenset({"htcondor"})


def is_synchronous_site(site: str) -> bool:
    """Whether ``site`` runs synchronously (Parsl) with no pollable WMS run.

    On synchronous sites a missing ``run_id`` is legitimate (the job already
    finished during ``bps submit``); on asynchronous sites (HTCondor) it means
    run-id extraction failed and the poll strategy is unavailable.
    """
    return site in _PARSL_SITES


def wms_service_fqn_for_site(site: str) -> str | None:
    """WMS service class FQN for a site, or ``None`` if unknown.

    Mirrors the ``wmsServiceClass`` in ``bps/sites/{site}.yaml``. Only the
    asynchronous (HTCondor) FQN is used by the run-id WMS fallback; the Parsl
    FQN is returned for completeness but its ``report`` is unimplemented.
    """
    if site in _HTCONDOR_SITES:
        return "lsst.ctrl.bps.htcondor.HTCondorService"
    if site in _PARSL_SITES:
        return "lsst.ctrl.bps.parsl.ParslService"
    return None


@dataclass
class BPSConfig:
    """Configuration for BPS submission.

    Attributes:
        pipeline: Pipeline to run (calibs, science, dia, fphot)
        night: Observing night in YYYYMMDD format
        site: Compute site (slurm, htcondor, local)
        band: Filter band for DIA pipeline
        template_collection: Template collection for DIA
        object_filter: Optional object name filter
        coord_collection: Coordinate collection for forced photometry
        operator: Username for output collections
        project: Project/account for HPC allocation (None → the active
            profile's name, lowercased)
        dry_run: If True, show what would be submitted without running
        extra_args: Additional arguments to pass to bps submit
    """

    pipeline: str
    night: str
    site: str = "slurm"
    band: str | None = None
    template_collection: str | None = None
    object_filter: str | None = None
    coord_collection: str | None = None
    operator: str = field(default_factory=lambda: os.environ.get("USER", "stips"))
    # HPC allocation account. None → resolved from the active profile's
    # ``name.lower()`` at render time (F-021), rather than hardcoding "nickel".
    project: str | None = None
    dry_run: bool = False
    extra_args: list[str] = field(default_factory=list)

    # Pre-built quantum graph (used by BPSExecutor with pipeline="custom")
    qgraph_file: str | None = None
    output_run: str | None = None

    # HPC cluster options (used by singularity-slurm and slurm sites)
    container_image: str | None = None
    cores_per_node: int = 32
    mem_per_node: int = 128  # GB
    walltime: str = "04:00:00"
    partition: str = "normal"
    max_blocks: int = 10

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.pipeline not in VALID_PIPELINES:
            raise ValueError(
                f"Invalid pipeline '{self.pipeline}'. "
                f"Must be one of: {', '.join(VALID_PIPELINES)}"
            )
        if self.site not in VALID_SITES:
            raise ValueError(
                f"Invalid site '{self.site}'. "
                f"Must be one of: {', '.join(VALID_SITES)}"
            )
        # Validate night format
        if self.night != "00000000" and not re.match(r"^\d{8}$", self.night):
            raise ValueError(f"Invalid night format '{self.night}'. Expected YYYYMMDD.")


@dataclass
class BPSResult:
    """Result of a BPS submission.

    Attributes:
        success: Whether the submission succeeded
        submit_dir: Path to the BPS submit directory
        run_id: BPS run identifier (for status/cancel)
        qgraph_file: Path to the quantum graph file
        config_file: Path to the rendered config file
        error: Error message if submission failed
        stdout: Standard output from bps submit
        stderr: Standard error from bps submit
    """

    success: bool
    submit_dir: str | None = None
    run_id: str | None = None
    qgraph_file: str | None = None
    config_file: str | None = None
    error: str | None = None
    stdout: str | None = None
    stderr: str | None = None


def find_bps_config(pipeline: str, config: Config) -> Path:
    """Find the BPS configuration file for a pipeline.

    Args:
        pipeline: Pipeline name (calibs, science, dia, fphot)
        config: Pipeline configuration

    Returns:
        Path to the BPS config file

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    # Repo-root bps/pipelines directory (instrument_dir is instruments/<name>/)
    bps_dir = config.instrument_dir.parent.parent / "bps" / "pipelines"
    config_file = bps_dir / f"{pipeline}.yaml"

    if not config_file.exists():
        raise FileNotFoundError(
            f"BPS config not found: {config_file}\n" f"Expected at: {bps_dir}"
        )

    return config_file


def generate_timestamp() -> str:
    """Generate a timestamp string for run identification."""
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def render_bps_config(
    bps_cfg: BPSConfig,
    config: Config,
    output_dir: Path,
) -> Path:
    """Render a BPS config file with variable substitution.

    Takes a template BPS config and substitutes variables like {repo},
    {night}, {band}, etc. with actual values. Also copies necessary
    include files (base.yaml, site configs) to maintain relative paths.

    Args:
        bps_cfg: BPS submission configuration
        config: Pipeline configuration
        output_dir: Directory to write rendered config

    Returns:
        Path to the rendered config file
    """
    timestamp = generate_timestamp()
    prof = config.require_profile()

    # Default band / PS1 template collection follow the profile's band->template
    # policy: fall back to the first PS1-eligible band (ps1_band_map key) rather
    # than a hardcoded "r". For Nickel/CTIO1m this is "r", preserving behavior.
    default_band = bps_cfg.band or next(iter(prof.ps1_band_map), "r")
    # Resolve the HPC project account and BPS payload prefix from the active
    # profile rather than hardcoding "nickel" (F-021).
    project = bps_cfg.project or prof.name.lower()
    payload_prefix = prof.name.lower()

    # Load template config
    template_path = find_bps_config(bps_cfg.pipeline, config)
    template_content = template_path.read_text()

    # Build object filter string
    object_filter = ""
    if bps_cfg.object_filter:
        object_filter = (
            f" AND exposure.target_name={butler_str_literal(bps_cfg.object_filter)}"
        )

    # Variable substitutions
    variables = {
        "repo": str(config.repo),
        "night": bps_cfg.night,
        "timestamp": timestamp,
        # STIPS framework: the instrument is declarative (loaded by path from
        # INSTRUMENT_DIR); LSST machinery lives in obs_stips + stips (src-layout).
        "instrument_dir": str(config.instrument_dir),
        "obs_stips_dir": str(_PACKAGES_DIR / "obs_stips"),
        "stips_defaults": str(_PACKAGES_DIR / "obs_stips" / "instrument_defaults"),
        "stips_src": str(_PACKAGES_DIR / "stips" / "src"),
        "obs_data_package": prof.obs_data_package or "",
        # Resolve the data-package dir with the shared precedence (explicit
        # package_dir, co-located under the instrument dir, or the reference
        # packages/ layout) so a fork's data package need not live under the
        # framework packages/ directory.
        "instrument_data_dir": (
            str(_data_dir)
            if (_data_dir := resolve_data_package_dir(prof, config.instrument_dir))
            else ""
        ),
        "stack_dir": str(config.stack_dir),
        "cp_pipe_dir": str(config.cp_pipe_dir) if config.cp_pipe_dir else "",
        "raw_parent_dir": str(config.raw_parent_dir),
        "refcat_repo": str(config.refcat_repo) if config.refcat_repo else "",
        "computeSite": bps_cfg.site,
        "operator": bps_cfg.operator,
        "project": project,
        "payload_prefix": payload_prefix,
        "band": default_band,
        "template_collection": bps_cfg.template_collection
        or template_ps1(default_band),
        "coord_collection": bps_cfg.coord_collection or "",
        "object_filter": object_filter,
        "pipeline": bps_cfg.pipeline,
        # Pre-built quantum graph (custom pipeline)
        "qgraph_file": bps_cfg.qgraph_file or "",
        "output_run": bps_cfg.output_run or "",
        # HPC cluster options
        "container_image": bps_cfg.container_image or "",
        "cores_per_node": str(bps_cfg.cores_per_node),
        "mem_per_node": str(bps_cfg.mem_per_node),
        "walltime": bps_cfg.walltime,
        "partition": bps_cfg.partition,
        "max_blocks": str(bps_cfg.max_blocks),
        "run_dir": str(config.repo / "parsl_runinfo"),
    }

    # Perform substitution
    rendered = template_content
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))

    # Create output directory structure
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy the include files (base.yaml and site configs) to maintain relative paths
    # The pipeline configs use "../sites/{site}.yaml" which includes "../base.yaml"
    # We need to fix the include path since we're putting everything in the same directory
    bps_source_dir = template_path.parent.parent  # bps/ directory
    sites_dest = output_dir / "sites"
    sites_dest.mkdir(parents=True, exist_ok=True)

    # Copy base.yaml to output_dir with variable substitution
    # (sites reference ../base.yaml)
    base_yaml = bps_source_dir / "base.yaml"
    if base_yaml.exists():
        base_content = base_yaml.read_text()
        for key, value in variables.items():
            base_content = base_content.replace(f"{{{key}}}", str(value))
        (output_dir / "base.yaml").write_text(base_content)

    # Copy the specific site config (with variable substitution)
    site_yaml = bps_source_dir / "sites" / f"{bps_cfg.site}.yaml"
    if site_yaml.exists():
        site_content = site_yaml.read_text()
        for key, value in variables.items():
            site_content = site_content.replace(f"{{{key}}}", str(value))
        (sites_dest / f"{bps_cfg.site}.yaml").write_text(site_content)

    # Fix the include path in the rendered config
    # Change "../sites/{site}.yaml" to "./sites/{site}.yaml"
    rendered = rendered.replace(
        f"../sites/{bps_cfg.site}.yaml", f"./sites/{bps_cfg.site}.yaml"
    )

    # Write rendered config
    output_file = (
        output_dir / f"bps_{bps_cfg.pipeline}_{bps_cfg.night}_{timestamp}.yaml"
    )
    output_file.write_text(rendered)

    return output_file


#: Matches ``Run Id``/``Run ID``/``run_id`` followed by ``: <value>`` anywhere in
#: a line (tolerating a leading log prefix); the ``Run Name`` line is excluded by
#: the caller.
_RUN_ID_RE = re.compile(r"\brun[ _]?id\s*:\s*(\S+)", re.IGNORECASE)


def _extract_run_id(stdout: str) -> str | None:
    """Extract the BPS run id from ``bps submit`` stdout.

    The v30 submit banner prints ``Run Id: <id>`` followed by ``Run Name: <name>``
    (``ctrl_bps.drivers.submit_driver``). Match ``Run Id``/``Run ID``/``run_id``
    case-insensitively (and tolerate a leading log/timestamp prefix) while
    explicitly excluding the ``Run Name:`` line — a superset of the original
    ``"Run ID:" in line or "run_id:" in line`` substring check, which the prior
    ``startswith("run id")`` fix had inadvertently narrowed (it dropped the
    ``run_id:`` underscore variant and any prefixed line).
    """
    for line in stdout.splitlines():
        if "run name" in line.lower():
            continue
        match = _RUN_ID_RE.search(line)
        if match:
            return match.group(1).strip()
    return None


def _match_run_id(runs: list[dict], output_run: str) -> str | None:
    """Pick the ``wms_id`` of the run matching ``output_run`` from a WMS listing.

    ``output_run`` is the RUN collection this submission targets — it is rendered
    into the BPS config as ``outputRun`` and is unique (it carries a timestamp),
    so it identifies the just-submitted workflow among the WMS's recent runs.
    ``WmsRunReport`` exposes it via ``run`` (and the payload/path echo pieces of
    it), so we match defensively across those fields but require a **single**
    unambiguous match — otherwise we return ``None`` and let the caller degrade
    loudly rather than poll the wrong run.
    """
    if not output_run:
        return None

    matched: list[str] = []
    for r in runs:
        wms_id = r.get("wms_id")
        if not wms_id:
            continue
        for key in ("run", "payload", "path"):
            value = r.get(key) or ""
            if output_run == value or output_run in value:
                matched.append(str(wms_id))
                break

    if len(matched) == 1:
        return matched[0]
    return None


def _resolve_run_id_via_wms(
    bps_cfg: BPSConfig,
    config: Config,
) -> str | None:
    """Recover a run id from the WMS when the submit banner did not yield one.

    Structured fallback for asynchronous (HTCondor) submissions: list recent WMS
    runs via ``bps_report.list_runs`` (``retrieve_report(run_id=None)``) and match
    the one whose RUN collection equals ``bps_cfg.output_run``. Returns ``None``
    when the WMS is unavailable, returns nothing, or does not match uniquely — the
    caller then treats the run id as genuinely unavailable.

    Not attempted on synchronous (Parsl) sites: there is no pollable run there, so
    a missing banner id is expected rather than something to recover.
    """
    if is_synchronous_site(bps_cfg.site):
        return None

    fqn = wms_service_fqn_for_site(bps_cfg.site)
    if not fqn:
        return None

    from stips.core import bps_report

    runs = bps_report.list_runs(config, wms_service_fqn=fqn)
    if not runs:
        return None

    return _match_run_id(runs, bps_cfg.output_run or "")


def submit(
    bps_cfg: BPSConfig,
    config: Config,
) -> BPSResult:
    """Submit a BPS workflow.

    This function:
    1. Renders the BPS config with variable substitution
    2. Creates a submit directory
    3. Runs `bps submit` with the rendered config

    Args:
        bps_cfg: BPS submission configuration
        config: Pipeline configuration

    Returns:
        BPSResult with submission status and details
    """
    from stips.core.stack import run_with_stack

    # Create submit directory
    submit_dir = config.repo / "bps" / f"{bps_cfg.pipeline}_{bps_cfg.night}"
    submit_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Render the BPS config
        rendered_config = render_bps_config(bps_cfg, config, submit_dir)

        # For dry-run, just return the rendered config without submitting
        if bps_cfg.dry_run:
            return BPSResult(
                success=True,
                submit_dir=str(submit_dir),
                config_file=str(rendered_config),
            )

        # Build bps submit command
        cmd = [
            "bps",
            "submit",
            str(rendered_config),
        ]

        cmd.extend(bps_cfg.extra_args)

        # Run the submission
        result = run_with_stack(
            cmd,
            config,
            capture_output=True,
            check=False,  # Don't raise on non-zero exit
            cwd=submit_dir,
        )

        success = result.returncode == 0

        # Layered run-id extraction, most-reliable-first:
        #   1. the submit banner (cheap; works on v30 —
        #      ``ctrl_bps.drivers.submit_driver`` prints ``Run Id: <id>``).
        #   2. structured WMS fallback (query ``retrieve_report`` and match this
        #      submission's output RUN collection) when the banner parse fails.
        # The CLI ``bps submit`` invocation is kept as-is on purpose: an
        # in-process submit would change ctrl_bps config/logging semantics and is
        # too risky to fold into this fix. Only run-id *recovery* is layered.
        run_id = None
        if success:
            run_id = _extract_run_id(result.stdout or "")
            if run_id is None:
                run_id = _resolve_run_id_via_wms(bps_cfg, config)
                if run_id is None and not is_synchronous_site(bps_cfg.site):
                    # Async site with no recoverable run id: no longer silent.
                    # The executor turns this into a loud, degraded mode rather
                    # than misclassifying it as a finished synchronous backend.
                    log.error(
                        "bps submit (site=%s) succeeded but no run id could be "
                        "extracted from the banner or recovered from the WMS "
                        "(output_run=%s); WMS polling is unavailable for this run.",
                        bps_cfg.site,
                        bps_cfg.output_run or "",
                    )

        return BPSResult(
            success=success,
            submit_dir=str(submit_dir),
            run_id=run_id,
            config_file=str(rendered_config),
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.stderr if not success else None,
        )

    except FileNotFoundError as e:
        return BPSResult(
            success=False,
            submit_dir=str(submit_dir),
            error=str(e),
        )
    except Exception as e:
        return BPSResult(
            success=False,
            submit_dir=str(submit_dir),
            error=f"Unexpected error: {e}",
        )


def status(run_id: str, config: Config) -> dict:
    """Check the status of a BPS run.

    Args:
        run_id: BPS run identifier
        config: Pipeline configuration

    Returns:
        Dictionary with status information
    """
    from stips.core.stack import run_with_stack

    try:
        result = run_with_stack(
            ["bps", "report", run_id],
            config,
            capture_output=True,
            check=False,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else None,
        }
    except Exception as e:
        return {
            "success": False,
            "output": None,
            "error": str(e),
        }


def cancel(run_id: str, config: Config) -> bool:
    """Cancel a BPS run.

    Args:
        run_id: BPS run identifier
        config: Pipeline configuration

    Returns:
        True if cancellation succeeded, False otherwise
    """
    from stips.core.stack import run_with_stack

    try:
        result = run_with_stack(
            ["bps", "cancel", run_id],
            config,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_runs(config: Config) -> list[dict]:
    """List recent BPS runs.

    Args:
        config: Pipeline configuration

    Returns:
        List of run information dictionaries
    """
    from stips.core.stack import run_with_stack

    try:
        result = run_with_stack(
            ["bps", "report"],
            config,
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            return []

        # Parse output into run entries
        runs = []
        for line in result.stdout.splitlines():
            # Basic parsing - format depends on WMS
            if line.strip() and not line.startswith("#"):
                runs.append({"raw": line.strip()})

        return runs
    except Exception:
        return []
