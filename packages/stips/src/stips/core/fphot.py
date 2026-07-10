"""Forced photometry at specified RA/Dec coordinates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core import butler_query
from stips.core.pipeline import (
    REFCATS_CHAIN,
    generate_run_timestamp,
    night_day_obs_expr,
    resolve_processccd_collections,
    validate_night,
)

VALID_IMAGE_TYPES = frozenset({"visit", "diffim", "both"})

if TYPE_CHECKING:
    from stips.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class ForcedPhotResult:
    """Result of forced photometry."""

    success: bool
    night: str
    output_collections: list[str] = field(default_factory=list)
    error: str | None = None


def _collection_has_difference_images(
    collection: str,
    config: Config,
    *,
    band: str | None,
) -> bool:
    """Check whether a diff run has at least one difference_image for the band."""
    prof = config.require_profile()
    query = f"instrument='{prof.name}'"
    if band:
        query += f" AND band='{band}'"

    return butler_query.has_datasets(
        config, "difference_image", collection, where=query
    )


def _select_diff_collection(
    night: str,
    config: Config,
    *,
    band: str | None,
) -> tuple[str | None, list[str]]:
    """Select the newest diff collection that contains datasets for this band."""
    prof = config.require_profile()
    candidates = sorted(
        butler_query.list_collections(
            config,
            f"{prof.collection_prefix}/runs/{night}/diff/*/run",
            prefix=f"{prof.collection_prefix}/",
        )
        or [],
        reverse=True,
    )
    for coll in candidates:
        if _collection_has_difference_images(coll, config, band=band):
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
    jobs: int = 1,
    log_file: Path | None = None,
    executor=None,
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
    from stips.core.executor import LocalExecutor

    if image_type not in VALID_IMAGE_TYPES:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=(
                f"Invalid image_type {image_type!r}; expected one of "
                f"{sorted(VALID_IMAGE_TYPES)}."
            ),
        )

    if executor is None:
        executor = LocalExecutor()

    prof = config.require_profile()
    night = validate_night(night)
    run_ts = generate_run_timestamp()
    repo = str(config.repo)

    output_collections: list[str] = []
    errors: list[str] = []

    # Find the processCcd collection: prefer the newest CHAINED parent (includes
    # primary + fallback results) over individual RUN collections.
    parent_collections = resolve_processccd_collections(config, night)
    processccd_coll = parent_collections[0] if parent_collections else None

    if not processccd_coll:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=f"No processCcd collection found for {night}. Run 'nickel science' first.",
        )

    log.info(f"Using processCcd collection: {processccd_coll}")

    # Build data query. A Lick observing night spans two UT days
    # (pre-/post-midnight); include both so pre-midnight exposures are not
    # dropped from forced photometry.
    data_query = f"instrument='{prof.name}' AND {night_day_obs_expr(night, prof)}"
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
                f"{prof.collection_prefix}/runs/{night}/forcedPhotRaDec/"
                f"{run_ts}/visit{band_suffix}"
            )
            output_run = f"{output_coll}/run"

            visit_input = (
                f"{processccd_coll},{prof.collection_prefix}/calib/current,"
                f"{REFCATS_CHAIN},{prof.skymap_collection}"
            )

            log.info("Running forced photometry on visit images...")
            log.info(f"  Input: {visit_input}")
            log.info(f"  Output: {output_coll}")

            result = executor.run_pipetask(
                [
                    "run",
                    "-b",
                    repo,
                    "--input",
                    visit_input,
                    "--output",
                    output_coll,
                    "--output-run",
                    output_run,
                    "-j",
                    str(jobs),
                    "--register-dataset-types",
                    "--pipeline",
                    f"{config.resolve_pipeline('ForcedPhotRaDec.yaml')}#visit-image",
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
                night, config, band=band
            )

            if not diff_coll:
                band_msg = f" for band '{band}'" if band else ""
                err_msg = (
                    f"No diff collection with difference_image datasets found for "
                    f"{night}{band_msg}. DIA may not have produced results for this "
                    f"night/band. Candidates checked: {', '.join(diff_candidates) or 'none'}"
                )
                log.warning(err_msg)
                errors.append(err_msg)

            if diff_coll:
                input_colls = (
                    f"{processccd_coll},{diff_coll},"
                    f"{prof.collection_prefix}/calib/current,"
                    f"{REFCATS_CHAIN},{prof.skymap_collection}"
                )
                band_suffix = f"_{band}" if band else ""
                output_coll = (
                    f"{prof.collection_prefix}/runs/{night}/forcedPhotRaDec/"
                    f"{run_ts}/diffim{band_suffix}"
                )
                output_run = f"{output_coll}/run"

                log.info("Running forced photometry on difference images...")
                log.info(f"  Input: {input_colls}")
                log.info(f"  Output: {output_coll}")

                result = executor.run_pipetask(
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
                        "-j",
                        str(jobs),
                        "--register-dataset-types",
                        "--pipeline",
                        f"{config.resolve_pipeline('ForcedPhotRaDec.yaml')}#diffim",
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
