"""Forced photometry at specified RA/Dec coordinates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import generate_run_timestamp, validate_night
from obs_nickel_data_tools.core.stack import run_butler, run_pipetask

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class ForcedPhotResult:
    """Result of forced photometry."""

    success: bool
    night: str
    output_collections: list[str] = field(default_factory=list)
    error: str | None = None


def _parse_collections(output: str) -> list[str]:
    """Parse butler query-collections output to get collection names."""
    lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
    # Skip header lines (first 2-3 lines are headers)
    # Look for lines that look like collection paths
    colls = []
    for line in lines:
        # Skip header/separator lines
        if line.startswith("-") or line.startswith("="):
            continue
        if line.startswith("type") or line.startswith("Name"):
            continue
        # Extract first column (collection name)
        parts = line.split()
        if parts and parts[0].startswith("Nickel/"):
            colls.append(parts[0])
    return colls


def run(
    night: str,
    ra: float,
    dec: float,
    config: Config,
    *,
    band: str | None = None,
    image_type: str = "diffim",
) -> ForcedPhotResult:
    """Run forced photometry at specified coordinates.

    Performs forced photometry at arbitrary sky positions on:
    - Calibrated visit images (preliminary_visit_image)
    - Difference images (difference_image)

    Args:
        night: Observing night (YYYYMMDD)
        ra: Right ascension in degrees
        dec: Declination in degrees
        config: Pipeline configuration
        band: Filter by band (default: all bands)
        image_type: 'visit', 'diffim', or 'both' (default: diffim)

    Returns:
        ForcedPhotResult with output collections
    """
    night = validate_night(night)
    run_ts = generate_run_timestamp()
    repo = str(config.repo)
    obs_nickel = str(config.obs_nickel)

    output_collections: list[str] = []
    errors: list[str] = []

    # Find processCcd collection
    result = run_butler(
        ["query-collections", repo, f"Nickel/runs/{night}/processCcd/*/run"],
        config,
        capture_output=True,
        check=False,
    )

    processccd_coll = None
    if result.returncode == 0:
        colls = _parse_collections(result.stdout)
        if colls:
            processccd_coll = sorted(colls)[-1]  # Latest

    if not processccd_coll:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=f"No processCcd collection found for {night}. Run 'nickel science' first.",
        )

    log.info(f"Using processCcd collection: {processccd_coll}")

    # Build data query
    data_query = "instrument='Nickel'"
    if band:
        data_query += f" AND band='{band}'"

    # Format coordinates for config (as Python list syntax)
    ra_config = f"[{ra}]"
    dec_config = f"[{dec}]"

    try:
        # Run on visit images
        if image_type in ("visit", "both"):
            band_suffix = f"_{band}" if band else ""
            output_coll = (
                f"Nickel/runs/{night}/forcedPhotRaDec/{run_ts}/visit{band_suffix}"
            )
            output_run = f"{output_coll}/run"

            log.info("Running forced photometry on visit images...")
            log.info(f"  Input: {processccd_coll}")
            log.info(f"  Output: {output_coll}")

            result = run_pipetask(
                [
                    "run",
                    "--butler-config",
                    repo,
                    "--input",
                    processccd_coll,
                    "--output",
                    output_coll,
                    "--output-run",
                    output_run,
                    "--register-dataset-types",
                    "--pipeline",
                    f"{obs_nickel}/pipelines/ForcedPhotRaDec.yaml#visit-image",
                    "--data-query",
                    data_query,
                    "-c",
                    "forcedPhotRaDec:useConfigCoords=True",
                    "-c",
                    f"forcedPhotRaDec:ra={ra_config}",
                    "-c",
                    f"forcedPhotRaDec:dec={dec_config}",
                ],
                config,
                capture_output=True,
                check=False,
            )

            if result.returncode == 0:
                output_collections.append(output_coll)
                log.info("  Visit image forced photometry completed")
            else:
                err_msg = f"Visit image forced photometry failed: {result.stderr or result.stdout}"
                log.warning(err_msg)
                errors.append(err_msg)

        # Run on difference images
        if image_type in ("diffim", "both"):
            # Find diff collection
            diff_result = run_butler(
                ["query-collections", repo, f"Nickel/runs/{night}/diff/*/run"],
                config,
                capture_output=True,
                check=False,
            )

            diff_coll = None
            if diff_result.returncode == 0:
                colls = _parse_collections(diff_result.stdout)
                if colls:
                    diff_coll = sorted(colls)[-1]

            if not diff_coll:
                err_msg = (
                    f"No diff collection found for {night}. Run 'nickel dia' first."
                )
                log.warning(err_msg)
                errors.append(err_msg)
            else:
                input_colls = f"{processccd_coll},{diff_coll}"
                band_suffix = f"_{band}" if band else ""
                output_coll = (
                    f"Nickel/runs/{night}/forcedPhotRaDec/{run_ts}/diffim{band_suffix}"
                )
                output_run = f"{output_coll}/run"

                log.info("Running forced photometry on difference images...")
                log.info(f"  Input: {input_colls}")
                log.info(f"  Output: {output_coll}")

                result = run_pipetask(
                    [
                        "run",
                        "--butler-config",
                        repo,
                        "--input",
                        input_colls,
                        "--output",
                        output_coll,
                        "--output-run",
                        output_run,
                        "--register-dataset-types",
                        "--pipeline",
                        f"{obs_nickel}/pipelines/ForcedPhotRaDec.yaml#diffim",
                        "--data-query",
                        data_query,
                        "-c",
                        "forcedPhotDiffimRaDec:useConfigCoords=True",
                        "-c",
                        f"forcedPhotDiffimRaDec:ra={ra_config}",
                        "-c",
                        f"forcedPhotDiffimRaDec:dec={dec_config}",
                    ],
                    config,
                    capture_output=True,
                    check=False,
                )

                if result.returncode == 0:
                    output_collections.append(output_coll)
                    log.info("  Difference image forced photometry completed")
                else:
                    err_msg = f"Diffim forced photometry failed: {result.stderr or result.stdout}"
                    log.warning(err_msg)
                    errors.append(err_msg)

        if output_collections:
            return ForcedPhotResult(
                success=True,
                night=night,
                output_collections=output_collections,
            )
        else:
            return ForcedPhotResult(
                success=False,
                night=night,
                error=(
                    "; ".join(errors)
                    if errors
                    else "No forced photometry outputs produced"
                ),
            )

    except Exception as e:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=str(e),
        )
