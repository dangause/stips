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

from stips.core import butler_query, dataset_types
from stips.core.pipeline import (
    REFCATS_CHAIN,
    generate_run_timestamp,
    resolve_processccd_collections,
)
from stips.core.query import butler_str_literal
from stips.core.stack import (
    run_butler,
    run_butler_python,
    run_butler_python_json,
    run_pipetask,
)

if TYPE_CHECKING:
    from stips.core.config import Config

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
    skymap: str | None = None,
) -> int | None:
    """Find the tract ID that contains the given coordinates.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        config: Pipeline configuration
        skymap: Skymap name (defaults to the active profile's skymap_name)

    Returns:
        Tract ID or None if not found
    """
    prof = config.require_profile()
    if skymap is None:
        skymap = prof.skymap_name
    script = f"""
import lsst.daf.butler as dafButler
from lsst.geom import SpherePoint, degrees

butler = dafButler.Butler({str(config.repo)!r})
skymap = butler.get('skyMap', skymap={str(skymap)!r}, collections={str(prof.skymap_collection)!r})
coord = SpherePoint({ra}, {dec}, degrees)
tract_info = skymap.findTract(coord)
print(tract_info.getId())
"""
    output = run_butler_python(script, config)
    if output:
        # The last line should be the tract ID
        for line in reversed(output.splitlines()):
            line = line.strip()
            if line.isdigit():
                return int(line)

    log.warning(f"Failed to find tract for RA={ra}, Dec={dec}")
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

    try:
        if butler_query.has_datasets(
            config,
            dataset_types.TEMPLATE_COADD,
            collection,
            where=f"band={butler_str_literal(band)}",
        ):
            return collection
    except Exception as e:
        log.debug(f"Failed to check template existence for {collection}: {e}")

    return None


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
        try:
            # Prefer the newest CHAINED parent over individual RUN collections
            # (the parent aggregates the primary and any fallback configs), and
            # verify it actually holds data for the requested band.
            resolved = resolve_processccd_collections(
                config,
                night,
                verify_datasets=True,
                dataset_type=dataset_types.PRELIMINARY_VISIT_IMAGE,
                where=f"band={butler_str_literal(band)}",
            )
            if resolved:
                coll = resolved[0]
                collections.append(coll)
                log.info(f"  Found {night} -> {coll}")
            else:
                log.info(f"  Night {night} has no {band}-band data (skipping)")

        except Exception as e:
            log.warning(f"Failed to find collection for {night}: {e}")

    return collections


def find_degenerate_wcs_visits(
    band: str,
    input_collections: list[str],
    config: "Config",
) -> list[int]:
    """Find visits whose WCS is degenerate (too few astrometric matches).

    A degenerate WCS fit (<=3 astrometric matches for a 6-parameter affine
    transformation) has 0 degrees of freedom, producing near-zero residuals.
    This passes LSST's quality check (distMean < maxMeanDistanceArcsec)
    but the WCS can be wildly incorrect, causing sheared warps in the coadd.

    Detected via the visit_summary: degenerate fits have astromOffsetMean
    and astromOffsetStd on the order of ~1e-11 arcsec (floating-point
    residuals from the zero-DOF fit), while well-constrained WCS solutions
    produce values >= ~0.002 arcsec.  A threshold of 1e-6 arcsec safely
    separates the two populations with >3 orders of magnitude margin.

    Args:
        band: Filter band
        input_collections: Collections containing science outputs
        config: Pipeline configuration

    Returns:
        List of visit IDs with degenerate WCS to exclude from coaddition.
    """
    # Threshold in arcsec: degenerate fits produce ~1e-11, real fits produce >= ~0.002
    DEGEN_THRESHOLD = 1e-6

    # Validate the band and embed the WHERE expression as a Python literal (!r)
    # so it cannot break out of the generated snippet's string (F-018).
    band_where = f"band={butler_str_literal(band)}"

    script = f"""
import json
import sys
import lsst.daf.butler as dafButler

butler = dafButler.Butler({str(config.repo)!r})
collections = {input_collections!r}
threshold = {DEGEN_THRESHOLD}

bad_visits = set()
for coll in collections:
    try:
        refs = list(butler.registry.queryDatasets(
            'preliminary_visit_summary',
            collections=[coll],
            where={band_where!r}
        ))
        for ref in refs:
            visit_id = ref.dataId['visit']
            summary = butler.get(ref)
            tbl = summary.asAstropy()
            for row in tbl:
                mean = float(row['astromOffsetMean'])
                std = float(row['astromOffsetStd'])
                if mean < threshold and std < threshold:
                    bad_visits.add(visit_id)
    except Exception as e:
        print(f"WARNING: WCS check failed for {{coll}}: {{e}}", file=sys.stderr)

print(json.dumps(sorted(bad_visits)))
"""
    result = run_butler_python_json(script, config)
    if isinstance(result, list):
        if result:
            log.info(
                f"WCS quality check found {len(result)} degenerate visits "
                f"(astromOffset < {DEGEN_THRESHOLD} arcsec): {result}"
            )
        else:
            log.info("WCS quality check: all visits OK")
        return result
    log.warning("WCS quality check script failed — no visits excluded")
    return []


def _remove_run_collections(
    runs: list[str],
    repo: str,
    config: Config,
    log_file: Path | None,
) -> None:
    """Remove orphaned template RUN collections, logging (never raising) on failure.

    Called only AFTER a replacement template has been built, verified, and the
    parent chain redefined to point at the new run — so these runs are no longer
    chain members and deleting them cannot destroy the live template. Leaving an
    old run orphaned is acceptable; aborting an already-successful rebuild
    because cleanup failed is not, so every failure is downgraded to a WARNING.
    """
    for old_run in runs:
        try:
            result = run_butler(
                ["remove-collections", repo, old_run, "--no-confirm"],
                config,
                check=False,
                log_file=log_file,
            )
            if result.returncode != 0:
                log.warning(
                    f"Failed to remove superseded template run {old_run} "
                    f"(exit {result.returncode}); leaving it orphaned"
                )
        except Exception as e:  # noqa: BLE001 - cleanup must never abort a success
            log.warning(f"Failed to remove superseded template run {old_run}: {e}")


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

    prof = config.require_profile()

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
            collection_name = f"templates/deep/tract{tract}/{band}"
            try:
                if butler_query.collection_exists(config, collection_name):
                    log.info(
                        f"Stale collection {collection_name} exists without data, will rebase"
                    )
                    needs_rebase = True
            except Exception as e:
                log.debug(f"Failed to check stale collection {collection_name}: {e}")

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

    # Filter out visits with degenerate WCS solutions.
    # A degenerate WCS (<=3 astrometric matches) has 0 degrees of freedom
    # and always produces 0 residual, passing LSST's quality check but
    # producing wildly incorrect WCS that causes sheared warps.
    bad_wcs_visits = find_degenerate_wcs_visits(band, input_collections, config)
    if bad_wcs_visits:
        log.warning(
            f"Excluding {len(bad_wcs_visits)} visits with degenerate WCS "
            f"(0 astrometric residual = too few matches): {bad_wcs_visits}"
        )

    repo = str(config.repo)
    run_ts = generate_run_timestamp()
    template_parent = f"templates/deep/tract{tract}/{band}"
    template_run = f"{template_parent}/{run_ts}"
    pipeline = config.resolve_pipeline("DRP.yaml")

    qg_dir = config.repo / "qgraphs"
    qg_dir.mkdir(parents=True, exist_ok=True)
    qg_file = qg_dir / f"template_t{tract}_{band}_{run_ts}.qg"

    try:
        # Build-then-swap sequencing (F-009).
        #
        # OLD (destructive) order: on a rebase the parent chain was emptied
        # (collection-chain --mode redefine) and the parent removed
        # (remove-collections) *before* the replacement was built. A failed
        # build — the common case (template overlap / WCS issues) — therefore
        # left NO template at all, with no rollback, and the removal's own
        # failure was swallowed by check=False.
        #
        # NEW order: (1) build the coadd into a fresh timestamped RUN, passing
        # no --output CHAINED collection so the build cannot touch the live
        # template; (2) verify the new RUN actually holds template_coadd; (3)
        # only then redefine the parent chain to the new RUN (one atomic swap);
        # (4) then remove the now-de-chained old RUNs, best-effort. If the build
        # or verification fails, the existing template is left completely
        # untouched.

        # Snapshot the existing template's RUN collections up front so they can
        # be cleaned up *after* a verified swap. Nothing is deleted here.
        old_runs: list[str] = []
        if needs_rebase:
            existing_runs = butler_query.list_collections(
                config, f"{template_parent}/*"
            )
            if existing_runs:
                old_runs = [c for c in existing_runs if c != template_run]

        # Register instrument (idempotent)
        run_butler(
            ["register-instrument", repo, prof.instrument_class],
            config,
            check=False,
            log_file=log_file,
        )

        # Build input chain
        input_chain = ",".join(input_collections)
        full_input = (
            f"{input_chain},{prof.collection_prefix}/calib/current,"
            f"{REFCATS_CHAIN},{prof.skymap_collection}"
        )

        data_query = (
            f"instrument='{prof.name}' AND skymap='{prof.skymap_name}' "
            f"AND tract={tract} AND band='{band}'"
        )

        # Exclude visits with degenerate WCS from the coadd
        if bad_wcs_visits:
            visit_csv = ", ".join(str(v) for v in bad_wcs_visits)
            data_query += f" AND visit NOT IN ({visit_csv})"

        # Build config args
        config_args: list[str] = []
        if config_files:
            for cf in config_files:
                config_args.extend(["--config-file", cf])

        # Build quantum graph into the new RUN only. No --output CHAINED
        # collection is passed: the existing template chain is left untouched
        # until the new outputs are built and verified below.
        qgraph_args = [
            "qgraph",
            "-b",
            repo,
            "-p",
            f"{pipeline}#coadds-only",
            "-i",
            full_input,
            "--output-run",
            template_run,
            "--save-qgraph",
            str(qg_file),
            "-d",
            data_query,
        ] + config_args

        run_pipetask(qgraph_args, config, log_file=log_file)

        # Run coadd pipeline
        run_pipetask(
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
            log_file=log_file,
        )

        # Verify the NEW run actually produced template_coadd datasets BEFORE
        # touching the existing template. On failure, leave the old template in
        # place and report the build as failed.
        if not butler_query.has_datasets(
            config,
            dataset_types.TEMPLATE_COADD,
            template_run,
            where=f"band={butler_str_literal(band)}",
        ):
            return CoaddResult(
                success=False,
                band=band,
                tract=tract,
                nights_used=nights,
                error=(
                    f"Coadd pipeline ran but produced no template_coadd datasets "
                    f"in {template_run} for band={band}, tract={tract}. Existing "
                    f"template (if any) left untouched. Check pipeline logs."
                ),
            )

        # Verified: atomically swap the parent chain to point at the new run.
        # In a rebase this also drops the old runs from the chain, which must
        # happen before they can be removed.
        run_butler(
            [
                "collection-chain",
                repo,
                template_parent,
                template_run,
                "--mode",
                "redefine",
            ],
            config,
            log_file=log_file,
        )

        # Now that the old runs are no longer chain members, clean them up
        # (best-effort — failures are logged, never fatal).
        if old_runs:
            _remove_run_collections(old_runs, repo, config, log_file)

        collection = template_parent
        log.info(f"Coadd template built: {collection}")
        return CoaddResult(
            success=True,
            band=band,
            collection=collection,
            tract=tract,
            nights_used=nights,
        )

    except Exception as e:
        return CoaddResult(
            success=False,
            band=band,
            tract=tract,
            nights_used=nights,
            error=str(e),
        )
