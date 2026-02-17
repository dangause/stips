"""Nickel Processing Suite CLI.

Unified command-line interface for processing Nickel telescope data
with the LSST Science Pipelines.

Usage:
    nickel calibs 20240625
    nickel science 20240625
    nickel dia 20240625 --auto-template
    nickel env

Profiles:
    nickel -p 2023ixf dia 20230519 --auto   # Uses .env.2023ixf
    nickel -p 2020wnt calibs 20201207       # Uses .env.2020wnt
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from obs_nickel_data_tools.core import config as cfg_module


def _print_error(msg: str) -> None:
    """Print error message in red."""
    click.secho(f"Error: {msg}", fg="red", err=True)


def _print_success(msg: str) -> None:
    """Print success message in green."""
    click.secho(msg, fg="green")


def _print_info(msg: str) -> None:
    """Print info message."""
    click.echo(msg)


def _resolve_env_file(env_file: Path | None, profile: str | None) -> Path | None:
    """Resolve environment file from --env-file or --profile."""
    if env_file:
        return env_file

    if profile:
        # Try common patterns for profile env files
        candidates = [
            Path(f".env.{profile}"),
            Path(f".env.{profile}.ps1"),
            Path(f"envs/{profile}.env"),
            Path(f".env-{profile}"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # If no match found, default to .env.{profile}
        default = Path(f".env.{profile}")
        if not default.exists():
            _print_error(
                f"Profile '{profile}' not found. Tried: {', '.join(str(c) for c in candidates)}"
            )
            sys.exit(1)
        return default

    return None


@click.group()
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    help="Environment file to load (default: .env)",
)
@click.option(
    "-p",
    "--profile",
    help="Profile name (loads .env.{profile})",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging (DEBUG level)",
)
@click.pass_context
def cli(
    ctx: click.Context, env_file: Path | None, profile: str | None, verbose: bool
) -> None:
    """Nickel Processing Suite - LSST pipeline tools for Nickel telescope data.

    Process Nickel 1-meter telescope observations using LSST Science Pipelines.
    Configure your environment with a .env file or environment variables.

    \b
    Quick start:
        nickel env                    # Check configuration
        nickel calibs 20240625        # Run calibrations
        nickel science 20240625       # Process science frames
        nickel dia 20240625 --auto    # Difference imaging

    \b
    Using profiles (shorthand for --env-file):
        nickel -p 2023ixf env         # Uses .env.2023ixf
        nickel -p 2020wnt calibs ...  # Uses .env.2020wnt
    """
    # Configure logging for all core modules
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(levelname)s] %(message)s",
    )

    ctx.ensure_object(dict)

    if env_file and profile:
        _print_error("Cannot use both --env-file and --profile")
        sys.exit(1)

    resolved = _resolve_env_file(env_file, profile)
    ctx.obj["env_file"] = resolved
    ctx.obj["profile"] = profile


def _load_config(
    ctx: click.Context,
    inline_env: dict[str, str] | None = None,
    prefer_inline: bool = False,
) -> cfg_module.Config:
    """Load configuration from context.

    Args:
        ctx: Click context
        inline_env: Inline environment variables (from YAML)
        prefer_inline: If True, inline_env overrides os.environ (for YAML configs)
    """
    env_file = ctx.obj.get("env_file")
    try:
        return cfg_module.load(
            env_file=env_file, inline_env=inline_env, prefer_inline=prefer_inline
        )
    except ValueError as e:
        _print_error(str(e))
        sys.exit(1)


# =============================================================================
# env - Show configuration
# =============================================================================


@cli.command()
@click.pass_context
def env(ctx: click.Context) -> None:
    """Show current configuration and validate paths."""
    try:
        config = _load_config(ctx)
    except SystemExit:
        return

    click.echo("\nNickel Processing Suite Configuration")
    click.echo("=" * 40)

    # Show profile/env file if set
    profile = ctx.obj.get("profile")
    env_file = ctx.obj.get("env_file")
    if profile:
        click.echo(f"\n{'Profile:':<20} {profile}")
    if env_file:
        click.echo(f"{'Env file:':<20} {env_file}")

    click.echo(f"\n{'REPO:':<20} {config.repo}")
    click.echo(f"{'STACK_DIR:':<20} {config.stack_dir}")
    click.echo(f"{'OBS_NICKEL:':<20} {config.obs_nickel}")
    click.echo(f"{'RAW_PARENT_DIR:':<20} {config.raw_parent_dir}")

    if config.cp_pipe_dir:
        click.echo(f"{'CP_PIPE_DIR:':<20} {config.cp_pipe_dir}")
    if config.refcat_repo:
        click.echo(f"{'REFCAT_REPO:':<20} {config.refcat_repo}")
    if config.lick_archive_dir:
        click.echo(f"{'LICK_ARCHIVE_DIR:':<20} {config.lick_archive_dir}")

    # Validate paths
    errors = config.validate()
    if errors:
        click.echo("\n" + click.style("Validation errors:", fg="red"))
        for err in errors:
            click.echo(f"  - {err}")
        sys.exit(1)
    else:
        click.echo("\n" + click.style("✓ All paths valid", fg="green"))

    # Check stack
    click.echo("\nChecking LSST stack...", nl=False)
    from obs_nickel_data_tools.core.stack import check_stack

    if check_stack(config):
        click.echo(click.style(" ✓ available", fg="green"))
    else:
        click.echo(click.style(" ✗ not accessible", fg="red"))
        click.echo("  Make sure LSST stack is installed at STACK_DIR")


# =============================================================================
# calibs - Nightly calibrations
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=4, help="Parallel jobs (default: 4)")
@click.pass_context
def calibs(ctx: click.Context, night: str, jobs: int) -> None:
    """Run nightly calibrations (bias, flat, defects).

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel calibs 20240625
        nickel calibs 20240625 --jobs 8
    """
    config = _load_config(ctx)

    _print_info(f"Running calibrations for {night}...")

    from obs_nickel_data_tools.core import calibs as calibs_module

    result = calibs_module.run(night, config, jobs=jobs)

    if result.success:
        _print_success(f"\n✓ Calibrations complete for {night}")
        click.echo(f"  Raw collection: {result.raw_run}")
        click.echo(f"  Bias: {result.cp_bias}")
        click.echo(f"  Flat: {result.cp_flat}")
        click.echo(f"  Calib chain: {result.calib_chain}")
    else:
        _print_error(f"Calibrations failed: {result.error}")
        sys.exit(1)


# =============================================================================
# science - Science processing
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=8, help="Parallel jobs (default: 8)")
@click.option("--bad", help="Comma-separated exposure IDs to exclude")
@click.option(
    "--bad-file",
    type=click.Path(exists=True, path_type=Path),
    help="File with bad exposure IDs",
)
@click.option("--object", "object_filter", help="Filter by OBJECT header value")
@click.option("--skip-coadds", is_flag=True, help="Skip coadd generation")
@click.option(
    "--config",
    "science_config",
    type=click.Path(exists=True, path_type=Path),
    help="Override calibrateImage config",
)
@click.option(
    "--ra", type=float, help="Target RA in degrees (enables coordinate validation)"
)
@click.option(
    "--dec", type=float, help="Target Dec in degrees (enables coordinate validation)"
)
@click.pass_context
def science(
    ctx: click.Context,
    night: str,
    jobs: int,
    bad: str | None,
    bad_file: Path | None,
    object_filter: str | None,
    skip_coadds: bool,
    science_config: Path | None,
    ra: float | None,
    dec: float | None,
) -> None:
    """Run science processing (ISR, WCS, photometry).

    NIGHT is the observing date in YYYYMMDD format.

    When --ra and --dec are provided, exposures with coordinates far from
    the target are automatically excluded to prevent qgraph failures from
    missing reference catalog coverage.

    \b
    Example:
        nickel science 20240625
        nickel science 20240625 --object 2020wnt --skip-coadds
        nickel science 20240625 --bad 12345,12346
        nickel science 20240625 --object 2023ixf --ra 210.91 --dec 54.32
    """
    if (ra is None) != (dec is None):
        _print_error("--ra and --dec must be provided together")
        sys.exit(1)

    config = _load_config(ctx)

    _print_info(f"Running science processing for {night}...")

    from obs_nickel_data_tools.core import science as science_module

    result = science_module.run(
        night,
        config,
        jobs=jobs,
        bad_exposures=bad,
        bad_file=bad_file,
        object_filter=object_filter,
        skip_coadds=skip_coadds,
        science_config=science_config,
        target_ra=ra,
        target_dec=dec,
    )

    if result.success:
        _print_success(f"\n✓ Science processing complete for {night}")
        click.echo(f"  Science run: {result.science_run}")
        if result.coadd_run:
            click.echo(f"  Coadd run: {result.coadd_run}")
    else:
        _print_error(f"Science processing failed: {result.error}")
        sys.exit(1)


# =============================================================================
# dia - Difference imaging
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("-j", "--jobs", default=8, help="Parallel jobs (default: 8)")
@click.option("-t", "--template", help="Template collection to use")
@click.option("--auto", "auto_template", is_flag=True, help="Auto-discover template")
@click.option("--prefer-ps1", is_flag=True, help="Prefer PS1 templates (with --auto)")
@click.option("-b", "--band", help="Filter by band (b/v/r/i)")
@click.option("--object", "object_filter", help="Filter by OBJECT header value")
@click.option("--bad", help="Comma-separated exposure IDs to exclude")
@click.option(
    "--bad-file",
    type=click.Path(exists=True, path_type=Path),
    help="File with bad exposure IDs",
)
@click.pass_context
def dia(
    ctx: click.Context,
    night: str,
    jobs: int,
    template: str | None,
    auto_template: bool,
    prefer_ps1: bool,
    band: str | None,
    object_filter: str | None,
    bad: str | None,
    bad_file: Path | None,
) -> None:
    """Run difference imaging analysis.

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel dia 20240625 --auto
        nickel dia 20240625 --template templates/deep/r
        nickel dia 20240625 --auto --band r --object 2020wnt
    """
    if not template and not auto_template:
        _print_error("Specify --template or --auto")
        sys.exit(1)

    config = _load_config(ctx)

    _print_info(f"Running difference imaging for {night}...")

    from obs_nickel_data_tools.core import dia as dia_module

    result = dia_module.run(
        night,
        config,
        jobs=jobs,
        template=template,
        auto_template=auto_template,
        prefer_ps1=prefer_ps1,
        band=band,
        object_filter=object_filter,
        bad_exposures=bad,
        bad_file=bad_file,
    )

    if result.success:
        _print_success(f"\n✓ Difference imaging complete for {night}")
        click.echo(f"  Template: {result.template_collection}")
        click.echo(f"  DIA run: {result.diff_run}")
        click.echo(f"  Difference images: {result.diff_image_count}")
        click.echo(f"  DIA sources: {result.dia_source_count}")
    else:
        _print_error(f"Difference imaging failed: {result.error}")
        sys.exit(1)


# =============================================================================
# download - Fetch data from archive
# =============================================================================


@cli.command()
@click.argument("night")
@click.option("--overwrite", is_flag=True, help="Re-download existing files")
@click.pass_context
def download(ctx: click.Context, night: str, overwrite: bool) -> None:
    """Download a night from the Lick archive.

    NIGHT is the observing date in YYYYMMDD format.

    \b
    Example:
        nickel download 20240625
    """
    config = _load_config(ctx)

    _print_info(f"Downloading {night} from Lick archive...")

    # Use existing fetch_archive_night module
    # Build args for the existing main()
    import sys

    from obs_nickel_data_tools.pipeline_tools import fetch_archive_night

    old_argv = sys.argv
    sys.argv = [
        "obsn-archive-fetch-night",
        "--night",
        night,
        "--raw-root",
        str(config.raw_parent_dir),
    ]
    if config.lick_archive_dir:
        sys.argv.extend(["--client-path", str(config.lick_archive_dir)])
    if overwrite:
        sys.argv.append("--overwrite")

    try:
        result = fetch_archive_night.main()
        sys.argv = old_argv
        if result == 0:
            _print_success(f"✓ Downloaded {night}")
        else:
            sys.exit(result)
    except SystemExit as e:
        sys.argv = old_argv
        if e.code != 0:
            sys.exit(e.code)


# =============================================================================
# bootstrap - Initialize a new Butler repository
# =============================================================================


@cli.command()
@click.argument(
    "config_file", type=click.Path(exists=True, path_type=Path), required=False
)
@click.pass_context
def bootstrap(ctx: click.Context, config_file: Path | None) -> None:
    """Initialize a new Butler repository.

    Creates the Butler repo, registers the instrument, ingests reference
    catalogs, and sets up the skymap. Run this once before processing data.

    Configuration can be provided in three ways (in order of precedence):

    \b
    1. Pipeline YAML file with 'env' section (recommended):
       nickel bootstrap scripts/config/2023ixf/pipeline_ps1_template.yaml

    \b
    2. Profile flag:
       nickel -p 2023ixf bootstrap

    \b
    3. Environment file:
       nickel --env-file .env.2023ixf bootstrap

    \b
    Examples:
        nickel bootstrap scripts/config/2023ixf/pipeline_ps1_template.yaml
        nickel bootstrap scripts/config/2020wnt/pipeline_nickel_template.yaml
        nickel -p 2023ixf bootstrap
    """
    from obs_nickel_data_tools.core import bootstrap as bootstrap_module
    from obs_nickel_data_tools.core import run as run_module

    inline_env = None

    # If a pipeline YAML is provided, extract env from it
    if config_file:
        yaml_env = run_module.get_env_from_yaml(config_file)
        if yaml_env:
            inline_env = yaml_env
            _print_info(f"Using environment from: {config_file}")
        else:
            # Check for profile in YAML
            cli_profile = ctx.obj.get("profile")
            if not cli_profile:
                yaml_profile = run_module.get_profile_from_yaml(config_file)
                if yaml_profile:
                    resolved = _resolve_env_file(None, yaml_profile)
                    if resolved:
                        ctx.obj["env_file"] = resolved
                        ctx.obj["profile"] = yaml_profile
                        _print_info(
                            f"Using profile '{yaml_profile}' from: {config_file}"
                        )

    # When loading from YAML with inline env, prefer YAML values
    prefer_inline = inline_env is not None
    config = _load_config(ctx, inline_env=inline_env, prefer_inline=prefer_inline)

    _print_info("Bootstrapping Butler repository...")
    _print_info(f"  Repo: {config.repo}")

    result = bootstrap_module.run(config)

    if result.success:
        _print_success("✓ Bootstrap complete")
        click.echo(f"  Repository ready: {config.repo}")
    else:
        _print_error(f"Bootstrap failed: {result.error}")
        sys.exit(1)


# =============================================================================
# clean - Remove processing runs from Butler repo
# =============================================================================


@cli.command()
@click.argument(
    "config_file", type=click.Path(exists=True, path_type=Path), required=False
)
@click.option(
    "--night",
    "nights",
    multiple=True,
    help="Only clean this night (repeatable, e.g. --night 20201207 --night 20201219)",
)
@click.option(
    "--step",
    "steps",
    multiple=True,
    type=click.Choice(["science", "dia", "fphot", "coadd"]),
    help="Only clean this step (repeatable, e.g. --step science --step dia)",
)
@click.option(
    "--dry-run", is_flag=True, help="List what would be removed without deleting"
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.pass_context
def clean(
    ctx: click.Context,
    config_file: Path | None,
    nights: tuple[str, ...],
    steps: tuple[str, ...],
    dry_run: bool,
    yes: bool,
) -> None:
    """Remove processing runs from the Butler repository.

    Deletes science (processCcd), DIA (diff), forced photometry, and per-night
    coadd runs. Preserves raws, calibrations, reference catalogs, skymaps,
    and templates.

    Configuration can come from a pipeline YAML, profile, or env file
    (same as other commands).

    \b
    Examples:
        # Preview what would be removed
        nickel clean pipeline.yaml --dry-run

    \b
        # Remove all processing runs
        nickel clean pipeline.yaml -y

    \b
        # Remove only DIA and forced phot runs
        nickel clean pipeline.yaml --step dia --step fphot

    \b
        # Remove runs for specific nights only
        nickel clean pipeline.yaml --night 20201207 --night 20201219

    \b
        # Using profile instead of YAML
        nickel -p 2020wnt clean --dry-run
    """
    from obs_nickel_data_tools.core import clean as clean_module
    from obs_nickel_data_tools.core import run as run_module

    inline_env = None

    # If a pipeline YAML is provided, extract env from it
    if config_file:
        yaml_env = run_module.get_env_from_yaml(config_file)
        if yaml_env:
            inline_env = yaml_env
        else:
            cli_profile = ctx.obj.get("profile")
            if not cli_profile:
                yaml_profile = run_module.get_profile_from_yaml(config_file)
                if yaml_profile:
                    resolved = _resolve_env_file(None, yaml_profile)
                    if resolved:
                        ctx.obj["env_file"] = resolved
                        ctx.obj["profile"] = yaml_profile

    # When loading from YAML with inline env, prefer YAML values
    prefer_inline = inline_env is not None
    config = _load_config(ctx, inline_env=inline_env, prefer_inline=prefer_inline)

    nights_list = list(nights) if nights else None
    steps_list = list(steps) if steps else None

    # First show what would be removed
    _print_info(f"Repository: {config.repo}")
    if nights_list:
        _print_info(f"Nights: {', '.join(nights_list)}")
    if steps_list:
        _print_info(f"Steps: {', '.join(steps_list)}")

    # Dry-run or preview
    preview = clean_module.run(
        config,
        nights=nights_list,
        steps=steps_list,
        dry_run=True,
    )

    if not preview.collections_removed:
        _print_info("No processing runs found to remove")
        return

    _print_info(f"\nFound {len(preview.collections_removed)} collections to remove:")
    for col in preview.collections_removed:
        click.echo(f"  {col}")

    if dry_run:
        _print_info("\n[DRY RUN] No changes made")
        return

    # Confirm
    if not yes:
        click.echo()
        if not click.confirm(f"Remove {len(preview.collections_removed)} collections?"):
            click.echo("Cancelled")
            return

    # Do the actual removal
    result = clean_module.run(
        config,
        nights=nights_list,
        steps=steps_list,
        dry_run=False,
    )

    if result.success:
        _print_success(f"\n✓ Removed {len(result.collections_removed)} collections")
    else:
        _print_error("Some collections could not be removed:")
        for err in result.errors:
            click.echo(f"  {err}")
        if result.collections_removed:
            click.echo(
                f"\n  ({len(result.collections_removed)} collections were removed successfully)"
            )
        sys.exit(1)


# =============================================================================
# ps1-template - Ingest PS1 template for DIA
# =============================================================================


@cli.command("ps1-template")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option(
    "-b",
    "--band",
    required=True,
    type=click.Choice(["r", "i"]),
    help="Nickel band (r or i)",
)
@click.option(
    "-c", "--collection", help="Output collection (default: templates/ps1/{band})"
)
@click.option("--tract", type=int, help="Tract number (auto-determined if not set)")
@click.option(
    "--size", type=float, default=0.2, help="Cutout size in degrees (default: 0.2)"
)
@click.option("--degrade-seeing", type=float, help="Convolve to this FWHM in arcsec")
@click.option("--overwrite", is_flag=True, help="Replace existing template")
@click.pass_context
def ps1_template(
    ctx: click.Context,
    ra: float,
    dec: float,
    band: str,
    collection: str | None,
    tract: int | None,
    size: float,
    degrade_seeing: float | None,
    overwrite: bool,
) -> None:
    """Download and ingest PS1 template for difference imaging.

    PS1 templates are available for r and i bands only.

    \b
    Example:
        nickel ps1-template --ra 210.91 --dec 54.32 --band r
        nickel ps1-template --ra 210.91 --dec 54.32 --band i --degrade-seeing 2.0
    """
    config = _load_config(ctx)

    _print_info(f"Ingesting PS1 {band}-band template at RA={ra:.4f}, Dec={dec:.4f}...")

    from obs_nickel_data_tools.core import ps1_template as ps1_module

    # Check if already exists
    target_collection = collection or f"templates/ps1/{band}"
    if not overwrite and ps1_module.check_exists(band, config, target_collection):
        _print_info(f"PS1 template already exists in {target_collection}")
        _print_info("Use --overwrite to replace")
        return

    result = ps1_module.run(
        ra=ra,
        dec=dec,
        band=band,
        config=config,
        collection=collection,
        tract=tract,
        size=size,
        degrade_seeing=degrade_seeing,
        overwrite=overwrite,
    )

    if result.success:
        _print_success("\n✓ PS1 template ingested")
        click.echo(f"  Collection: {result.collection}")
        if result.tract is not None:
            click.echo(f"  Tract: {result.tract}, Patch: {result.patch}")
        if result.fits_path:
            click.echo(f"  FITS file: {result.fits_path}")
    else:
        _print_error(f"PS1 template ingestion failed: {result.error}")
        sys.exit(1)


# =============================================================================
# fphot - Forced photometry at RA/Dec
# =============================================================================


@cli.command("fphot")
@click.argument("night")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option("-b", "--band", help="Filter by band (default: all bands)")
@click.option(
    "--image-type",
    type=click.Choice(["visit", "diffim", "both"]),
    default="diffim",
    help="Image type for photometry (default: diffim)",
)
@click.pass_context
def fphot(
    ctx: click.Context,
    night: str,
    ra: float,
    dec: float,
    band: str | None,
    image_type: str,
) -> None:
    """Run forced photometry at specified RA/Dec coordinates.

    Performs forced photometry on calibrated visit images and/or difference images.

    \b
    Example:
        nickel fphot 20230519 --ra 210.91 --dec 54.32
        nickel fphot 20230519 --ra 210.91 --dec 54.32 --band r --image-type both
    """
    config = _load_config(ctx)

    _print_info(
        f"Running forced photometry for {night} at RA={ra:.4f}, Dec={dec:.4f}..."
    )

    from obs_nickel_data_tools.core import fphot as fphot_module

    result = fphot_module.run(
        night=night,
        ra=ra,
        dec=dec,
        config=config,
        band=band,
        image_type=image_type,
    )

    if result.success:
        _print_success(f"\n✓ Forced photometry complete for {night}")
        for coll in result.output_collections:
            click.echo(f"  Collection: {coll}")
    else:
        _print_error(f"Forced photometry failed: {result.error}")
        sys.exit(1)


# =============================================================================
# lightcurve - Extract lightcurve from DIA sources
# =============================================================================


@cli.command("lightcurve")
@click.option("--ra", type=float, required=True, help="Right ascension in degrees")
@click.option("--dec", type=float, required=True, help="Declination in degrees")
@click.option(
    "--collections", required=True, help="Comma-separated DIA collections to query"
)
@click.option(
    "--radius", type=float, default=1.0, help="Match radius in arcsec (default: 1.0)"
)
@click.option(
    "--min-snr", type=float, default=3.0, help="Minimum S/N filter (default: 3.0)"
)
@click.option("-b", "--band", help="Restrict to single band")
@click.option("--name", help="Target name for plot title")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output CSV file")
@click.option("--plot/--no-plot", default=True, help="Generate plot (default: yes)")
@click.option(
    "--dataset-type",
    default="dia_source_unfiltered",
    help="Dataset type to query (default: dia_source_unfiltered). Use 'forced_phot_diffim_radec' for forced phot.",
)
@click.pass_context
def lightcurve(
    ctx: click.Context,
    ra: float,
    dec: float,
    collections: str,
    radius: float,
    min_snr: float,
    band: str | None,
    name: str | None,
    output: Path | None,
    plot: bool,
    dataset_type: str,
) -> None:
    """Extract lightcurve from DIA source catalogs or forced photometry.

    Queries source catalogs for detections near the specified coordinates
    and generates a lightcurve CSV and optional plot.

    \b
    Example (DIA sources):
        nickel lightcurve --ra 210.91 --dec 54.32 \\
            --collections "Nickel/runs/20230519/diff/*/run" --name "SN 2023ixf"

    Example (forced photometry):
        nickel lightcurve --ra 210.91 --dec 54.32 \\
            --collections "Nickel/runs/20230519/forcedPhotRaDec/*/run" \\
            --dataset-type forced_phot_diffim_radec --name "SN 2023ixf"
    """
    config = _load_config(ctx)

    _print_info(f"Extracting lightcurve at RA={ra:.4f}, Dec={dec:.4f}...")

    from obs_nickel_data_tools.core import lightcurve as lc_module

    result = lc_module.run(
        ra=ra,
        dec=dec,
        collections=collections,
        config=config,
        radius=radius,
        min_snr=min_snr,
        band=band,
        name=name,
        output=output,
        plot=plot,
        dataset_type=dataset_type,
    )

    if result.success:
        _print_success("\n✓ Lightcurve extracted")
        click.echo(f"  Detections: {result.n_detections}")
        if result.csv_path:
            click.echo(f"  CSV: {result.csv_path}")
        if result.plot_path:
            click.echo(f"  Plot: {result.plot_path}")
    else:
        _print_error(f"Lightcurve extraction failed: {result.error}")
        sys.exit(1)


# =============================================================================
# run - YAML-driven pipeline orchestrator
# =============================================================================


@cli.command("run")
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Print commands without executing")
@click.pass_context
def run_pipeline(
    ctx: click.Context,
    config_file: Path,
    dry_run: bool,
) -> None:
    """Run full pipeline from YAML configuration file.

    CONFIG_FILE is a YAML file specifying target, nights, bands, and options.
    The YAML can include environment configuration in two ways:

    \b
    1. 'profile' field - loads .env.{profile}
    2. 'env' section - inline environment variables (self-contained)

    \b
    Example with profile:
        profile: "2023ixf"    # Loads .env.2023ixf
        object: "2023ixf"
        ...

    \b
    Example with inline env (self-contained):
        env:
          REPO: "/path/to/repo"
          STACK_DIR: "/path/to/stack"
          OBS_NICKEL: "/path/to/obs_nickel"
          RAW_PARENT_DIR: "/path/to/raw"
        object: "2023ixf"
        ...

    \b
    Example:
        nickel run scripts/config/2023ixf/pipeline.yaml
        nickel run pipeline.yaml --dry-run
    """
    from obs_nickel_data_tools.core import run as run_module

    inline_env = None

    # Check if the YAML specifies inline env vars (highest priority)
    yaml_env = run_module.get_env_from_yaml(config_file)
    if yaml_env:
        inline_env = yaml_env
        _print_info("Using inline environment from pipeline YAML")
    else:
        # Check if the YAML specifies a profile and no -p flag was given
        cli_profile = ctx.obj.get("profile")
        if not cli_profile:
            yaml_profile = run_module.get_profile_from_yaml(config_file)
            if yaml_profile:
                # Resolve and use the YAML-specified profile
                resolved = _resolve_env_file(None, yaml_profile)
                if resolved:
                    ctx.obj["env_file"] = resolved
                    ctx.obj["profile"] = yaml_profile
                    _print_info(f"Using profile '{yaml_profile}' from pipeline YAML")

    # When loading from YAML with inline env, prefer YAML values over shell environment
    prefer_inline = inline_env is not None
    config = _load_config(ctx, inline_env=inline_env, prefer_inline=prefer_inline)

    _print_info(f"Running pipeline from {config_file}...")

    if dry_run:
        _print_info("[DRY RUN] Commands will be printed but not executed")

    result = run_module.run(
        config_file=config_file,
        config=config,
        dry_run=dry_run,
    )

    if result.success:
        _print_success("\n✓ Pipeline complete")
        if result.template_collections:
            click.echo("  Templates:")
            for band, coll in result.template_collections.items():
                click.echo(f"    {band}: {coll}")
        if result.lightcurve_path:
            click.echo(f"  Lightcurve: {result.lightcurve_path}")
        if result.log_dir:
            click.echo(f"  Logs: {result.log_dir}")
    else:
        _print_error(f"Pipeline failed: {result.error}")
        if result.failed_calibs:
            click.echo(f"  Failed calibs: {result.failed_calibs}")
        if result.failed_science:
            click.echo(f"  Failed science: {result.failed_science}")
        if result.failed_dia:
            click.echo(f"  Failed DIA: {result.failed_dia}")
        if result.log_dir:
            click.echo(f"  Logs: {result.log_dir}")
        sys.exit(1)


# =============================================================================
# bps - Batch Processing Service integration
# =============================================================================


@cli.group()
@click.pass_context
def bps(ctx: click.Context) -> None:
    """Submit and manage BPS workflows on HPC clusters.

    BPS (Batch Processing Service) enables large-scale parallel processing
    on Slurm, HTCondor, or local Parsl executors.

    \b
    Available sites:
        slurm     - Slurm clusters via Parsl
        htcondor  - HTCondor pools
        local     - Local machine (for testing)

    \b
    Example:
        nickel bps submit calibs 20230519 --site slurm
        nickel bps submit dia 20230519 --site slurm --band r
        nickel bps status RUN_ID
        nickel bps cancel RUN_ID
    """
    pass


@bps.command("submit")
@click.argument("pipeline", type=click.Choice(["calibs", "science", "dia", "fphot"]))
@click.argument("night")
@click.option(
    "--site",
    default="slurm",
    type=click.Choice(["slurm", "htcondor", "local"]),
    help="Compute site (default: slurm)",
)
@click.option("-b", "--band", help="Band for DIA pipeline (required for dia)")
@click.option("-t", "--template", help="Template collection for DIA")
@click.option("--object", "object_filter", help="Filter by OBJECT header")
@click.option("--coords", help="Coordinate collection for forced photometry")
@click.option("--project", default="nickel", help="HPC project/account")
@click.option("--dry-run", is_flag=True, help="Show what would be submitted")
@click.pass_context
def bps_submit(
    ctx: click.Context,
    pipeline: str,
    night: str,
    site: str,
    band: str | None,
    template: str | None,
    object_filter: str | None,
    coords: str | None,
    project: str,
    dry_run: bool,
) -> None:
    """Submit a pipeline to BPS for parallel execution.

    PIPELINE is one of: calibs, science, dia, fphot
    NIGHT is the observing date (YYYYMMDD)

    \b
    Example:
        nickel bps submit calibs 20230519 --site slurm
        nickel bps submit science 20230519 --site local --dry-run
        nickel bps submit dia 20230519 --site slurm --band r
    """
    # Validate DIA requires band
    if pipeline == "dia" and not band:
        _print_error("DIA pipeline requires --band option")
        sys.exit(1)

    config = _load_config(ctx)

    from obs_nickel_data_tools.core import bps as bps_module

    bps_cfg = bps_module.BPSConfig(
        pipeline=pipeline,
        night=night,
        site=site,
        band=band,
        template_collection=template,
        object_filter=object_filter,
        coord_collection=coords,
        project=project,
        dry_run=dry_run,
    )

    mode_str = "[DRY RUN] " if dry_run else ""
    _print_info(f"{mode_str}Submitting {pipeline} pipeline for {night} to {site}...")

    result = bps_module.submit(bps_cfg, config)

    if result.success:
        if dry_run:
            _print_success(f"[DRY RUN] Would submit to {site}")
            if result.config_file:
                click.echo(f"  Config file: {result.config_file}")
        else:
            _print_success("BPS workflow submitted")
        if result.submit_dir:
            click.echo(f"  Submit dir: {result.submit_dir}")
        if result.run_id:
            click.echo(f"  Run ID: {result.run_id}")
            click.echo(f"\n  Check status: nickel bps status {result.run_id}")
    else:
        _print_error(f"BPS submission failed: {result.error}")
        if result.stderr:
            click.echo(f"\nStderr:\n{result.stderr}")
        sys.exit(1)


@bps.command("status")
@click.argument("run_id")
@click.pass_context
def bps_status(ctx: click.Context, run_id: str) -> None:
    """Check status of a BPS run.

    RUN_ID is the identifier returned by bps submit.

    \b
    Example:
        nickel bps status 12345
    """
    config = _load_config(ctx)

    from obs_nickel_data_tools.core import bps as bps_module

    _print_info(f"Checking status of run {run_id}...")

    result = bps_module.status(run_id, config)

    if result.get("success"):
        click.echo(result.get("output", "No output"))
    else:
        _print_error(f"Failed to get status: {result.get('error', 'Unknown error')}")
        sys.exit(1)


@bps.command("cancel")
@click.argument("run_id")
@click.option("--force", is_flag=True, help="Force cancellation")
@click.pass_context
def bps_cancel(ctx: click.Context, run_id: str, force: bool) -> None:
    """Cancel a running BPS workflow.

    RUN_ID is the identifier returned by bps submit.

    \b
    Example:
        nickel bps cancel 12345
    """
    config = _load_config(ctx)

    from obs_nickel_data_tools.core import bps as bps_module

    if not force:
        if not click.confirm(f"Cancel run {run_id}?"):
            click.echo("Cancelled")
            return

    _print_info(f"Cancelling run {run_id}...")

    if bps_module.cancel(run_id, config):
        _print_success(f"Run {run_id} cancelled")
    else:
        _print_error(f"Failed to cancel run {run_id}")
        sys.exit(1)


@bps.command("list")
@click.pass_context
def bps_list(ctx: click.Context) -> None:
    """List recent BPS runs.

    \b
    Example:
        nickel bps list
    """
    config = _load_config(ctx)

    from obs_nickel_data_tools.core import bps as bps_module

    runs = bps_module.list_runs(config)

    if not runs:
        click.echo("No BPS runs found")
        return

    click.echo("Recent BPS runs:")
    for run in runs:
        click.echo(f"  {run.get('raw', run)}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
