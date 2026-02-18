"""Difference Image Analysis (DIA) pipeline."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import (
    INSTRUMENT,
    REFCATS_CHAIN,
    SKYMAPS_CHAIN,
    CollectionNames,
    build_exclusion_expr,
    night_to_day_obs,
    parse_bad_exposures,
    validate_night,
)
from obs_nickel_data_tools.core.stack import run_butler, run_pipetask

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


def _parse_quanta_summary(output: str, log_file: Path | None = None) -> tuple[int, int]:
    """Parse pipetask output for quanta success/failure counts.

    Returns:
        Tuple of (succeeded, failed) counts. Returns (0, 0) if not found.
    """
    succeeded = 0
    failed = 0
    pattern = re.compile(
        r"Executed (\d+) quanta successfully, (\d+) failed and (\d+) remain"
    )

    for line in output.splitlines():
        m = pattern.search(line)
        if m:
            succeeded = int(m.group(1))
            failed = int(m.group(2))

    if succeeded == 0 and failed == 0 and log_file and log_file.exists():
        try:
            with open(log_file) as f:
                for line in f:
                    m = pattern.search(line)
                    if m:
                        succeeded = int(m.group(1))
                        failed = int(m.group(2))
        except OSError:
            pass

    return succeeded, failed


def _is_empty_qgraph(output: str) -> bool:
    """Check if pipetask output indicates an empty quantum graph."""
    return "QuantumGraph contains no quanta" in output


@dataclass
class DIAResult:
    """Result of difference imaging."""

    success: bool
    night: str
    diff_run: str
    template_collection: str | None
    diff_image_count: int = 0
    dia_source_count: int = 0
    error: str | None = None


def find_template(
    config: Config,
    band: str | None = None,
    prefer_ps1: bool = False,
) -> str | None:
    """Auto-discover the best template collection.

    Args:
        config: Pipeline configuration
        band: Filter by band (b/v/r/i)
        prefer_ps1: Prefer PS1 templates over internal

    Returns:
        Template collection name, or None if not found
    """
    repo = str(config.repo)

    try:
        result = run_butler(
            ["query-collections", repo], config, capture_output=True, log_file=None
        )
    except Exception:
        return None

    candidates = []
    for line in result.stdout.splitlines():
        col = line.split()[0] if line.split() else ""
        if col.startswith("templates/") or col.startswith("coadds/"):
            candidates.append(col)

    if not candidates:
        return None

    # Filter by band if specified
    if band:
        candidates = [c for c in candidates if c.endswith(f"/{band}")]

    if not candidates:
        return None

    # Sort by preference
    if prefer_ps1:
        ps1 = [c for c in candidates if "ps1" in c.lower()]
        if ps1:
            return ps1[0]
    else:
        internal = [c for c in candidates if "templates/deep" in c]
        if internal:
            return internal[0]

    return candidates[0]


def run(
    night: str,
    config: Config,
    *,
    jobs: int = 8,
    template: str | None = None,
    auto_template: bool = False,
    prefer_ps1: bool = False,
    band: str | None = None,
    object_filter: str | None = None,
    bad_exposures: str | None = None,
    bad_file: Path | None = None,
    log_file: Path | None = None,
) -> DIAResult:
    """Run difference imaging for a night.

    Args:
        night: Observing night (YYYYMMDD)
        config: Pipeline configuration
        jobs: Number of parallel jobs
        template: Template collection to use
        auto_template: Auto-discover template
        prefer_ps1: Prefer PS1 templates (with auto_template)
        band: Filter by band (b/v/r/i)
        object_filter: Filter by OBJECT header value
        bad_exposures: Comma-separated exposure IDs to exclude
        bad_file: File with exposure IDs to exclude
        log_file: Optional path to write LSST pipeline logs

    Returns:
        DIAResult with collection names and counts
    """
    night = validate_night(night)
    cols = CollectionNames(night)
    repo = str(config.repo)
    day_obs = night_to_day_obs(night)

    # Resolve template
    template_collection = template
    if auto_template:
        template_collection = find_template(config, band=band, prefer_ps1=prefer_ps1)

    if not template_collection:
        return DIAResult(
            success=False,
            night=night,
            diff_run=cols.diff_run,
            template_collection=None,
            error="No template specified. Use --template or --auto-template",
        )

    # Find science collection
    try:
        result = run_butler(
            ["query-collections", repo], config, capture_output=True, log_file=log_file
        )
        sci_parent = None
        for line in result.stdout.splitlines():
            col = line.split()[0] if line.split() else ""
            if col.startswith(f"Nickel/runs/{night}/processCcd/") or col.startswith(
                f"Nickel/runs/{night}/science/"
            ):
                sci_parent = col

        if not sci_parent:
            return DIAResult(
                success=False,
                night=night,
                diff_run=cols.diff_run,
                template_collection=template_collection,
                error=f"No science collection found for night {night}. Run science processing first.",
            )
    except Exception as e:
        return DIAResult(
            success=False,
            night=night,
            diff_run=cols.diff_run,
            template_collection=template_collection,
            error=f"Failed to query collections: {e}",
        )

    # Build query
    bad_ids = parse_bad_exposures(bad_exposures, bad_file)
    exclusion_expr = build_exclusion_expr(bad_ids)

    object_expr = ""
    if object_filter:
        object_expr = f" AND exposure.target_name='{object_filter}'"

    band_expr = ""
    if band:
        band_expr = f" AND band='{band}'"

    data_query = (
        f"instrument='Nickel' AND exposure.observation_type='science' "
        f"AND day_obs={day_obs}{object_expr}{exclusion_expr}{band_expr}"
    )

    # Pipeline and config paths
    pipeline = config.obs_nickel / "pipelines" / "DIA.yaml"
    subtract_config = config.obs_nickel / "configs/dia/subtractImages.py"
    detect_config = config.obs_nickel / "configs/dia/detectAndMeasure.py"

    try:
        # Register instrument
        run_butler(
            ["register-instrument", repo, INSTRUMENT],
            config,
            check=False,
            log_file=log_file,
        )

        # Build quantum graph
        qg_dir = config.repo / "qgraphs"
        qg_dir.mkdir(parents=True, exist_ok=True)
        qg_file = qg_dir / f"diff_{night}_{cols.run_ts}.qg"

        # Find raw collection (optional for DIA)
        raw_run = ""
        result = run_butler(
            ["query-collections", repo], config, capture_output=True, log_file=log_file
        )
        for line in result.stdout.splitlines():
            col = line.split()[0] if line.split() else ""
            if col.startswith(f"Nickel/raw/{night}/"):
                raw_run = col
                break

        input_collections = f"{sci_parent},{cols.calib_chain},{REFCATS_CHAIN},{SKYMAPS_CHAIN},{template_collection}"
        if raw_run:
            input_collections = f"{sci_parent},{raw_run},{cols.calib_chain},{REFCATS_CHAIN},{SKYMAPS_CHAIN},{template_collection}"

        qgraph_args = [
            "qgraph",
            "-b",
            repo,
            "-p",
            f"{pipeline}#dia-full",
            "-i",
            input_collections,
            "-o",
            cols.diff_parent,
            "--output-run",
            cols.diff_run,
            "--save-qgraph",
            str(qg_file),
            "-d",
            data_query,
        ]

        if subtract_config.exists():
            qgraph_args.extend(["--config-file", f"subtractImages:{subtract_config}"])
        if detect_config.exists():
            qgraph_args.extend(
                ["--config-file", f"detectAndMeasureDiaSource:{detect_config}"]
            )

        qg_result = run_pipetask(
            qgraph_args,
            config,
            capture_output=True,
            check=False,
            log_file=log_file,
        )

        # Check for empty quantum graph (no matching data for this night/band)
        combined_qg_output = (qg_result.stdout or "") + (qg_result.stderr or "")
        if _is_empty_qgraph(combined_qg_output):
            log.warning(
                f"Empty quantum graph for {night}/{band or 'all'} — "
                f"no matching science data found for DIA"
            )
            return DIAResult(
                success=False,
                night=night,
                diff_run=cols.diff_run,
                template_collection=template_collection,
                error=f"No matching science data for DIA (empty quantum graph). "
                f"Query: {data_query}",
            )

        if qg_result.returncode != 0:
            return DIAResult(
                success=False,
                night=night,
                diff_run=cols.diff_run,
                template_collection=template_collection,
                error=f"QGraph build failed: {qg_result.stderr or qg_result.stdout}",
            )

        # Run DIA
        dia_result = run_pipetask(
            [
                "run",
                "-b",
                repo,
                "-g",
                str(qg_file),
                "-j",
                str(jobs),
                "--register-dataset-types",
            ],
            config,
            capture_output=True,
            check=False,
            log_file=log_file,
        )

        # Parse quanta counts to handle partial success
        combined_output = (dia_result.stdout or "") + (dia_result.stderr or "")
        quanta_ok, quanta_fail = _parse_quanta_summary(combined_output, log_file)

        if dia_result.returncode != 0 and quanta_ok == 0:
            return DIAResult(
                success=False,
                night=night,
                diff_run=cols.diff_run,
                template_collection=template_collection,
                error=f"DIA pipeline failed: {dia_result.stderr or dia_result.stdout}",
            )

        if quanta_fail > 0:
            log.warning(
                f"DIA partial success for {night}/{band or 'all'}: "
                f"{quanta_ok} quanta succeeded, {quanta_fail} failed"
            )

        # Update collection chain
        run_butler(
            [
                "collection-chain",
                repo,
                cols.diff_parent,
                cols.diff_run,
                "--mode",
                "redefine",
            ],
            config,
            log_file=log_file,
        )

        # Count outputs
        diff_count = 0
        src_count = 0
        try:
            result = run_butler(
                [
                    "query-datasets",
                    repo,
                    "difference_image",
                    "--collections",
                    cols.diff_run,
                    "--where",
                    f"instrument='Nickel' AND day_obs={day_obs}",
                ],
                config,
                capture_output=True,
                log_file=log_file,
            )
            diff_count = max(0, len(result.stdout.splitlines()) - 2)
        except Exception:
            pass

        try:
            result = run_butler(
                [
                    "query-datasets",
                    repo,
                    "dia_source_unfiltered",
                    "--collections",
                    cols.diff_run,
                    "--where",
                    f"instrument='Nickel' AND day_obs={day_obs}",
                ],
                config,
                capture_output=True,
                log_file=log_file,
            )
            src_count = max(0, len(result.stdout.splitlines()) - 2)
        except Exception:
            pass

        # If pipeline "succeeded" but produced no difference images, report failure.
        # This commonly happens when rewarpTemplate finds no template overlap for
        # any visit, so subtractImages is silently skipped by the framework.
        if diff_count == 0:
            log.warning(
                f"DIA pipeline ran but produced no difference images for "
                f"{night}/{band or 'all'} ({quanta_ok} quanta ran, "
                f"{quanta_fail} failed). Template may not overlap science visits."
            )
            return DIAResult(
                success=False,
                night=night,
                diff_run=cols.diff_run,
                template_collection=template_collection,
                diff_image_count=0,
                dia_source_count=0,
                error=(
                    f"No difference images produced ({quanta_ok} quanta ran, "
                    f"{quanta_fail} failed). Template may not overlap science visits."
                ),
            )

        return DIAResult(
            success=True,
            night=night,
            diff_run=cols.diff_run,
            template_collection=template_collection,
            diff_image_count=diff_count,
            dia_source_count=src_count,
        )

    except Exception as e:
        return DIAResult(
            success=False,
            night=night,
            diff_run=cols.diff_run,
            template_collection=template_collection,
            error=str(e),
        )
