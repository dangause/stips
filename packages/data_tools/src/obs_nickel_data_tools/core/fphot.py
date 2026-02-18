"""Forced photometry at specified RA/Dec coordinates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.pipeline import (
    butler_query_has_results,
    generate_run_timestamp,
    parse_butler_query_output,
    validate_night,
)
from obs_nickel_data_tools.core.stack import run_butler_query, run_pipetask

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


def _collection_has_difference_images(
    repo: str,
    collection: str,
    config: Config,
    *,
    band: str | None,
    log_file: Path | None,
) -> bool:
    """Check whether a diff run has at least one difference_image for the band."""
    query = "instrument='Nickel'"
    if band:
        query += f" AND band='{band}'"

    result = run_butler_query(
        [
            "query-data-ids",
            repo,
            "visit",
            "--datasets",
            "difference_image",
            "--collections",
            collection,
            "--where",
            query,
            "--limit",
            "1",
        ],
        config,
        check=False,
    )

    if result.returncode != 0:
        return False
    return butler_query_has_results(result.stdout or "")


def _select_diff_collection(
    repo: str,
    night: str,
    config: Config,
    *,
    band: str | None,
    log_file: Path | None,
) -> tuple[str | None, list[str]]:
    """Select the newest diff collection that contains datasets for this band."""
    diff_result = run_butler_query(
        ["query-collections", repo, f"Nickel/runs/{night}/diff/*/run"],
        config,
        check=False,
    )

    if diff_result.returncode != 0:
        return None, []

    candidates = sorted(
        parse_butler_query_output(diff_result.stdout, prefix_filter="Nickel/"),
        reverse=True,
    )
    for coll in candidates:
        if _collection_has_difference_images(
            repo, coll, config, band=band, log_file=log_file
        ):
            return coll, candidates
    return None, candidates


def run(
    night: str,
    ra: float,
    dec: float,
    config: Config,
    *,
    band: str | None = None,
    image_type: str = "diffim",
    log_file: Path | None = None,
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
        log_file: Optional path to write LSST pipeline logs

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
    # Prefer the CHAINED parent (includes primary + fallback results),
    # fall back to individual RUN collections for compatibility.
    processccd_coll = None
    for pattern in [
        f"Nickel/runs/{night}/processCcd/*",
        f"Nickel/runs/{night}/processCcd/*/run",
        f"Nickel/runs/{night}/processCcd/*/run_fb*",
    ]:
        result = run_butler_query(
            ["query-collections", repo, pattern],
            config,
            check=False,
        )
        if result.returncode == 0:
            colls = parse_butler_query_output(result.stdout, prefix_filter="Nickel/")
            if colls:
                # Prefer CHAINED parents over individual RUNs
                chained = [
                    c for c in colls if not c.endswith(("/run",)) and "/run_fb" not in c
                ]
                if chained:
                    processccd_coll = sorted(chained)[-1]
                else:
                    processccd_coll = sorted(colls)[-1]
                break

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
                    "-b",
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
                log_file=log_file,
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
            # Select a diff collection that actually contains the requested band.
            diff_coll, diff_candidates = _select_diff_collection(
                repo, night, config, band=band, log_file=log_file
            )

            if not diff_coll:
                band_msg = f" for band '{band}'" if band else ""
                err_msg = (
                    f"No diff collection with difference_image datasets found for "
                    f"{night}{band_msg}. DIA may not have produced results for this "
                    f"night/band. Candidates checked: {', '.join(diff_candidates) or 'none'}"
                )
                log.info(err_msg)
                errors.append(err_msg)

            if diff_coll:
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
                        "-b",
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
                    log_file=log_file,
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
