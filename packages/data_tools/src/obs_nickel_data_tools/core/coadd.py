"""Coadd template building for difference imaging.

This module builds deep coadd templates from multiple Nickel observations.
These templates are used for difference imaging when PS1 templates are
not available (B/V bands) or when better PSF matching is desired.

The workflow is:
1. Process template nights through calibs and science
2. Build coadd templates from the processed science images
3. Use the templates for DIA on science nights
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from obs_nickel_data_tools.core.stack import run_with_stack

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


@dataclass
class CoaddResult:
    """Result of coadd template building."""

    success: bool
    band: str
    collection: str | None = None
    tract: int | None = None
    nights_used: list[str] = field(default_factory=list)
    error: str | None = None


def find_tract_for_coords(
    ra: float,
    dec: float,
    config: Config,
    skymap: str = "nickelRings-v1",
) -> int | None:
    """Find the tract ID that contains the given coordinates.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        config: Pipeline configuration
        skymap: Skymap name

    Returns:
        Tract ID or None if not found
    """
    # Use butler to find tract
    # We query for any existing data to find the tract, or compute it
    args = [
        "python",
        "-c",
        f"""
import lsst.daf.butler as dafButler
from lsst.geom import SpherePoint, degrees

butler = dafButler.Butler('{config.repo}')
skymap = butler.get('skyMap', skymap='{skymap}', collections='skymaps/nickelRings')
coord = SpherePoint({ra}, {dec}, degrees)
tract_info = skymap.findTract(coord)
print(tract_info.getId())
""",
    ]

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)
        if result.returncode == 0:
            tract_str = result.stdout.strip()
            return int(tract_str)
    except Exception as e:
        log.warning(f"Failed to find tract for RA={ra}, Dec={dec}: {e}")

    return None


def check_template_exists(
    band: str,
    tract: int,
    config: Config,
) -> str | None:
    """Check if a coadd template already exists.

    Args:
        band: Filter band
        tract: Tract ID
        config: Pipeline configuration

    Returns:
        Collection name if template exists, None otherwise
    """
    collection = f"templates/deep/tract{tract}/{band}"

    args = [
        "butler",
        "query-datasets",
        str(config.repo),
        "template_coadd",
        "--collections",
        collection,
        "--where",
        f"band='{band}'",
    ]

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
            if len(lines) > 2:  # Header is 2 lines
                return collection
    except Exception:
        pass

    return None


def _parse_collection_names(output: str) -> list[str]:
    """Parse butler query-collections output to extract collection names.

    Handles various output formats from butler query-collections,
    including table headers, separators, and multi-column output.

    Args:
        output: Raw stdout from butler query-collections

    Returns:
        List of collection names found
    """
    collections = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Skip header/separator lines
        if line.startswith("-") or line.startswith("="):
            continue
        if line.lower().startswith("type") or line.lower().startswith("name"):
            continue
        # Extract the first column (collection name)
        parts = line.split()
        if parts:
            coll = parts[0]
            if coll.startswith("Nickel/"):
                collections.append(coll)
    return collections


def find_science_collections_for_nights(
    nights: list[str],
    band: str,
    config: Config,
) -> list[str]:
    """Find science run collections for the given nights and band.

    Args:
        nights: List of nights (YYYYMMDD format)
        band: Filter band
        config: Pipeline configuration

    Returns:
        List of collection names with science outputs for this band
    """
    collections = []

    for night in nights:
        # Look for processCcd collections for this night
        args = [
            "butler",
            "query-collections",
            str(config.repo),
            f"Nickel/runs/{night}/processCcd/*",
        ]

        try:
            result = run_with_stack(args, config, capture_output=True, check=False)
            if result.returncode != 0:
                log.warning(
                    f"  No processCcd collections found for {night}"
                    f"{': ' + result.stderr.strip() if result.stderr else ''}"
                )
                continue

            # Parse collection names from output
            night_colls = _parse_collection_names(result.stdout)
            if not night_colls:
                raw_output = result.stdout.strip()
                if "Nickel/" in raw_output:
                    log.warning(
                        f"  Could not parse processCcd collections for {night}; "
                        "unexpected query-collections output format"
                    )
                    log.debug(f"  Raw output: {raw_output[:500]}")
                else:
                    log.info(
                        f"  No processCcd collections found for {night} "
                        "(likely no successful science run)"
                    )
                continue

            # Prefer /run collections (RUN type) over parent (CHAINED type)
            # Sort so /run collections come first
            night_colls.sort(key=lambda c: (0 if c.endswith("/run") else 1, c))

            found = False
            for coll in night_colls:
                # Verify this collection has data for the requested band
                check_args = [
                    "butler",
                    "query-datasets",
                    str(config.repo),
                    "preliminary_visit_image",
                    "--collections",
                    coll,
                    "--where",
                    f"band='{band}'",
                    "--limit",
                    "1",
                ]
                check_result = run_with_stack(
                    check_args, config, capture_output=True, check=False
                )
                if check_result.returncode == 0:
                    check_lines = [
                        line
                        for line in check_result.stdout.strip().split("\n")
                        if line.strip()
                    ]
                    if len(check_lines) > 2:
                        collections.append(coll)
                        log.info(f"  Found {night} -> {coll}")
                        found = True
                        break

            if not found:
                log.info(f"  Night {night} has no {band}-band data (skipping)")

        except Exception as e:
            log.warning(f"Failed to find collection for {night}: {e}")

    return collections


def run(
    nights: list[str],
    band: str,
    config: Config,
    *,
    ra: float | None = None,
    dec: float | None = None,
    tract: int | None = None,
    jobs: int = 8,
    overwrite: bool = False,
    config_files: list[str] | None = None,
    log_file: Path | None = None,
) -> CoaddResult:
    """Build coadd template from multiple nights of Nickel observations.

    This runs the LSST coaddition pipeline to create a deep template
    from processed science images.

    Args:
        nights: List of nights to include (YYYYMMDD format)
        band: Filter band (b, v, r, i)
        config: Pipeline configuration
        ra: Target RA for tract determination (optional if tract provided)
        dec: Target Dec for tract determination (optional if tract provided)
        tract: Tract ID (auto-determined from ra/dec if not provided)
        jobs: Number of parallel jobs
        overwrite: Replace existing template if present
        config_files: Config override files for pipetask (e.g., ["makeDirectWarp:path/to/config.py"])
        log_file: Optional path to write LSST pipeline logs

    Returns:
        CoaddResult with collection and status
    """
    if not nights:
        return CoaddResult(
            success=False,
            band=band,
            error="No template nights provided",
        )

    # Determine tract
    if tract is None:
        if ra is not None and dec is not None:
            tract = find_tract_for_coords(ra, dec, config)
            if tract is None:
                return CoaddResult(
                    success=False,
                    band=band,
                    error=f"Could not determine tract for RA={ra}, Dec={dec}",
                )
        else:
            return CoaddResult(
                success=False,
                band=band,
                error="Must provide tract or (ra, dec) coordinates",
            )

    log.info(f"Building coadd template for band={band}, tract={tract}")
    log.info(f"Template nights: {nights}")

    # Check if template already exists
    needs_rebase = overwrite
    if not overwrite:
        existing = check_template_exists(band, tract, config)
        if existing:
            log.info(f"Template already exists: {existing}")
            return CoaddResult(
                success=True,
                band=band,
                collection=existing,
                tract=tract,
                nights_used=nights,
            )
        else:
            # No template data found. Check if a stale CHAINED collection
            # exists from a previous failed attempt — if so, rebase to clean it up.
            # If the collection doesn't exist at all, no rebase needed.
            collection_name = f"templates/deep/tract{tract}/{band}"
            check_args = [
                "butler",
                "query-collections",
                str(config.repo),
                collection_name,
            ]
            try:
                check_result = run_with_stack(
                    check_args, config, capture_output=True, check=False
                )
                if (
                    check_result.returncode == 0
                    and collection_name in check_result.stdout
                ):
                    log.info(
                        f"Stale collection {collection_name} exists without data, will rebase"
                    )
                    needs_rebase = True
            except Exception:
                pass

    # Find science collections for the template nights
    log.info("Finding science collections for template nights...")
    input_collections = find_science_collections_for_nights(nights, band, config)

    if not input_collections:
        return CoaddResult(
            success=False,
            band=band,
            tract=tract,
            error=f"No template nights have processed {band}-band data. "
            f"Check that template nights were observed in {band}-band "
            f"and that science processing succeeded for them.",
        )

    log.info(
        f"Found {len(input_collections)} of {len(nights)} template nights "
        f"with {band}-band data"
    )

    # Build the coadd using 30_coadds.sh
    script_path = config.obs_nickel.parent.parent / "scripts/pipeline/30_coadds.sh"
    if not script_path.exists():
        # Try alternate location
        script_path = config.obs_nickel / "../../scripts/pipeline/30_coadds.sh"
        script_path = script_path.resolve()

    if not script_path.exists():
        return CoaddResult(
            success=False,
            band=band,
            tract=tract,
            error=f"Coadd script not found: {script_path}",
        )

    # Build input collection string
    input_chain = ",".join(input_collections)

    # Prepare command arguments
    args = [
        str(script_path),
        "--tract",
        str(tract),
        "--band",
        band,
        "--input",
        input_chain,
        "--jobs",
        str(jobs),
    ]

    if needs_rebase:
        args.append("--rebase")

    if config_files:
        for cf in config_files:
            args.extend(["-C", cf])

    log.info(f"Running coadd build: {' '.join(args)}")

    try:
        result = run_with_stack(args, config, check=False, capture_output=True)

        if result.returncode == 0:
            collection = f"templates/deep/tract{tract}/{band}"
            log.info(f"Coadd template built: {collection}")
            return CoaddResult(
                success=True,
                band=band,
                collection=collection,
                tract=tract,
                nights_used=nights,
            )
        else:
            error_msg = f"Coadd pipeline failed (exit code {result.returncode})"
            if result.stderr:
                # Get last few lines of stderr for the most relevant error
                stderr_lines = result.stderr.strip().splitlines()
                tail = "\n".join(stderr_lines[-10:])
                error_msg += f"\n{tail}"
            elif result.stdout:
                stdout_lines = result.stdout.strip().splitlines()
                tail = "\n".join(stdout_lines[-10:])
                error_msg += f"\n{tail}"
            log.error(error_msg)
            return CoaddResult(
                success=False,
                band=band,
                tract=tract,
                nights_used=nights,
                error=error_msg,
            )

    except Exception as e:
        return CoaddResult(
            success=False,
            band=band,
            tract=tract,
            nights_used=nights,
            error=str(e),
        )


def process_template_nights(
    nights: list[str],
    bands: list[str],
    config: Config,
    *,
    object_filter: str | None = None,
    jobs: int = 8,
    log_file: Path | None = None,
) -> dict[str, bool]:
    """Process template nights through calibs and science.

    Before building coadd templates, the template nights need to be
    processed through the calibration and science pipelines.

    Args:
        nights: Template nights to process
        bands: Bands to process
        config: Pipeline configuration
        object_filter: Optional object name filter
        jobs: Parallel jobs
        log_file: Optional path to write LSST pipeline logs

    Returns:
        Dict mapping night to success status
    """
    from obs_nickel_data_tools.core import calibs, science

    results = {}

    for night in nights:
        log.info(f"Processing template night {night}...")

        # Run calibrations
        calib_result = calibs.run(night, config, jobs=jobs, log_file=log_file)
        if not calib_result.success:
            log.warning(
                f"Calibrations failed for template night {night}: {calib_result.error}"
            )
            results[night] = False
            continue

        # Run science processing
        sci_result = science.run(
            night,
            config,
            jobs=jobs,
            object_filter=object_filter,
            skip_coadds=True,
            bands=bands,
            log_file=log_file,
        )
        if not sci_result.success:
            log.warning(
                f"Science failed for template night {night}: {sci_result.error}"
            )
            results[night] = False
            continue

        results[night] = True
        log.info(f"Template night {night} processed successfully")

    return results
