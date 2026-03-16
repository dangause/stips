"""Forced photometry at specified RA/Dec coordinates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from small_tel_tools.core.pipeline import (
    REFCATS_CHAIN,
    butler_query_has_results,
    generate_run_timestamp,
    night_to_day_obs,
    parse_butler_query_output,
    validate_night,
)
from small_tel_tools.core.stack import run_butler_query

if TYPE_CHECKING:
    from small_tel_tools.core.config import Config
    from small_tel_tools.instruments.base import InstrumentPlugin

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
    instrument_name: str,
) -> bool:
    """Check whether a diff run has at least one difference_image for the band."""
    query = f"instrument='{instrument_name}'"
    if band:
        query += f" AND band='{band}'"

    result = run_butler_query(
        [
            "query-datasets",
            repo,
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
    collection_prefix: str,
    instrument_name: str,
) -> tuple[str | None, list[str]]:
    """Select the newest diff collection that contains datasets for this band."""
    diff_result = run_butler_query(
        ["query-collections", repo, f"{collection_prefix}/runs/{night}/diff/*/run"],
        config,
        check=False,
    )

    if diff_result.returncode != 0:
        return None, []

    candidates = sorted(
        parse_butler_query_output(
            diff_result.stdout, prefix_filter=f"{collection_prefix}/"
        ),
        reverse=True,
    )
    for coll in candidates:
        if _collection_has_difference_images(
            repo, coll, config, band=band, instrument_name=instrument_name
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
    jobs: int = 1,
    log_file: Path | None = None,
    executor=None,
    plugin: "InstrumentPlugin | None" = None,
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
        plugin: Instrument plugin (defaults to NickelPlugin for backward compat)

    Returns:
        ForcedPhotResult with output collections
    """
    from small_tel_tools.core.executor import LocalExecutor

    if plugin is None:
        from small_tel_tools.instruments.nickel import NickelPlugin

        plugin = NickelPlugin()

    if executor is None:
        executor = LocalExecutor()

    night = validate_night(night)
    run_ts = generate_run_timestamp()
    repo = str(config.repo)
    obs_package = str(config.obs_package)

    output_collections: list[str] = []
    errors: list[str] = []

    # Find processCcd collection
    # Prefer the CHAINED parent (includes primary + fallback results)
    # over individual RUN collections.
    processccd_coll = None
    result = run_butler_query(
        [
            "query-collections",
            repo,
            f"{plugin.collection_prefix}/runs/{night}/processCcd/*",
        ],
        config,
        check=False,
    )
    if result.returncode == 0:
        colls = parse_butler_query_output(
            result.stdout, prefix_filter=f"{plugin.collection_prefix}/"
        )
        if colls:
            # Prefer CHAINED parents over individual RUNs
            chained = [
                c for c in colls if not c.endswith(("/run",)) and "/run_fb" not in c
            ]
            if chained:
                processccd_coll = sorted(chained)[-1]
            else:
                processccd_coll = sorted(colls)[-1]

    if not processccd_coll:
        return ForcedPhotResult(
            success=False,
            night=night,
            error=f"No processCcd collection found for {night}. Run 'nickel science' first.",
        )

    log.info(f"Using processCcd collection: {processccd_coll}")

    # Build data query
    day_obs = night_to_day_obs(night, day_obs_offset=plugin.day_obs_offset)
    data_query = f"instrument='{plugin.name}' AND day_obs={day_obs}"
    if band:
        data_query += f" AND band='{band}'"

    # Format coordinates for config (as Python list syntax)
    ra_config = f"[{ra}]"
    dec_config = f"[{dec}]"

    try:
        # Run on visit images
        if image_type in ("visit", "both"):
            band_suffix = f"_{band}" if band else ""
            output_coll = f"{plugin.collection_prefix}/runs/{night}/forcedPhotRaDec/{run_ts}/visit{band_suffix}"
            output_run = f"{output_coll}/run"

            visit_input = f"{processccd_coll},{plugin.collection_prefix}/calib/current,{REFCATS_CHAIN},{plugin.skymaps_chain}"

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
                    f"{obs_package}/pipelines/ForcedPhotRaDec.yaml#visit-image",
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
                repo,
                night,
                config,
                band=band,
                collection_prefix=plugin.collection_prefix,
                instrument_name=plugin.name,
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
                input_colls = f"{processccd_coll},{diff_coll},{plugin.collection_prefix}/calib/current,{REFCATS_CHAIN},{plugin.skymaps_chain}"
                band_suffix = f"_{band}" if band else ""
                output_coll = f"{plugin.collection_prefix}/runs/{night}/forcedPhotRaDec/{run_ts}/diffim{band_suffix}"
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
                        f"{obs_package}/pipelines/ForcedPhotRaDec.yaml#diffim",
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
