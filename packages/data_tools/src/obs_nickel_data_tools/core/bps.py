"""BPS (Batch Processing Service) integration for Nickel Processing Suite.

This module provides functionality for submitting pipelines to HPC clusters
using LSST's BPS (Batch Processing Service) with Parsl or HTCondor backends.

Example usage:
    from obs_nickel_data_tools.core.bps import BPSConfig, submit

    bps_cfg = BPSConfig(
        pipeline="science",
        night="20230519",
        site="slurm",
    )
    result = submit(bps_cfg, config)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config


# Valid pipeline names
VALID_PIPELINES = ("calibs", "science", "dia", "fphot", "custom")

# Valid site names
VALID_SITES = ("slurm", "htcondor", "local", "singularity-slurm")


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
        project: Project/account for HPC allocation
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
    operator: str = field(default_factory=lambda: os.environ.get("USER", "nps"))
    project: str = "nickel"
    dry_run: bool = False
    extra_args: list[str] = field(default_factory=list)

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
    # Look in the bps/pipelines directory relative to obs_nickel
    bps_dir = config.obs_nickel.parent.parent / "bps" / "pipelines"
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

    # Load template config
    template_path = find_bps_config(bps_cfg.pipeline, config)
    template_content = template_path.read_text()

    # Build object filter string
    object_filter = ""
    if bps_cfg.object_filter:
        object_filter = f" AND exposure.target_name='{bps_cfg.object_filter}'"

    # Variable substitutions
    variables = {
        "repo": str(config.repo),
        "night": bps_cfg.night,
        "timestamp": timestamp,
        "obs_nickel": str(config.obs_nickel),
        "stack_dir": str(config.stack_dir),
        "cp_pipe_dir": str(config.cp_pipe_dir) if config.cp_pipe_dir else "",
        "raw_parent_dir": str(config.raw_parent_dir),
        "refcat_repo": str(config.refcat_repo) if config.refcat_repo else "",
        "computeSite": bps_cfg.site,
        "operator": bps_cfg.operator,
        "project": bps_cfg.project,
        "band": bps_cfg.band or "r",
        "template_collection": bps_cfg.template_collection
        or f"templates/ps1/{bps_cfg.band or 'r'}",
        "coord_collection": bps_cfg.coord_collection or "",
        "object_filter": object_filter,
        "pipeline": bps_cfg.pipeline,
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
    from obs_nickel_data_tools.core.stack import run_with_stack

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

        # Parse output for run ID
        run_id = None
        if result.stdout:
            # Look for run ID in output (format varies by WMS)
            for line in result.stdout.splitlines():
                if "Run ID:" in line or "run_id:" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        run_id = parts[1].strip()
                        break

        success = result.returncode == 0

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
    from obs_nickel_data_tools.core.stack import run_with_stack

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
    from obs_nickel_data_tools.core.stack import run_with_stack

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
    from obs_nickel_data_tools.core.stack import run_with_stack

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
