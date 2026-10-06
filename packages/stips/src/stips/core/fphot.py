"""Forced photometry at specified RA/Dec coordinates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core import butler_query, dataset_types
from stips.core.pipeline import (
    REFCATS_CHAIN,
    CollectionNames,
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
        config, dataset_types.DIFFERENCE_IMAGE, collection, where=query
    )


def _select_diff_collection(
    night: str,
    config: Config,
    *,
    band: str | None,
) -> tuple[str | None, list[str]]:
    """Select the diff collection(s) forced photometry should read.

    With a band: the newest diff run holding that band's difference images.
    Without one: every diff run holding difference images, newest first, as a
    comma-joined input list. Per-band DIA writes one run per band, so taking
    only the newest run would silently drop the other bands; listing them
    newest-first lets a re-run win for any visit it covers.
    """
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
    if band is None:
        with_diffs = [
            coll
            for coll in candidates
            if _collection_has_difference_images(coll, config, band=None)
        ]
        return (",".join(with_diffs) or None), candidates
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
    cols = CollectionNames(night, run_ts, prefix=prof.collection_prefix)
    repo = str(config.repo)

    output_collections: list[str] = []
    errors: list[str] = []

    # Science runs per band group (e.g. "r,i", then "rp", then "ip"), each into
    # its own processCcd CHAINED parent. Join ALL of them, as DIA does: taking
    # only the newest parent hid every other band group's calexps (2023ixf rp
    # photometry on 2 of ~17 nights in the v2.2.1 rebuild). Band groups are
    # disjoint by filter, so the parents never offer the same dataset twice.
    parent_collections = resolve_processccd_collections(config, night, all_parents=True)
    processccd_coll = ",".join(parent_collections) if parent_collections else None

    if not processccd_coll:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=f"No processCcd collection found for {night}. Run 'stips science' first.",
        )

    log.info(f"Using processCcd collection(s): {processccd_coll}")

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
            output_coll = cols.forced_phot_parent("visit", band)
            output_run = cols.forced_phot_run("visit", band)

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
                output_coll = cols.forced_phot_parent("diffim", band)
                output_run = cols.forced_phot_run("diffim", band)

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
