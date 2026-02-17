"""YAML-driven pipeline orchestrator.

This module reads a YAML configuration file and orchestrates the full pipeline:
calibs → science → DIA → forced photometry → lightcurve.

Example YAML format:
    # Environment configuration (choose one approach):
    #
    # Option 1: Reference a profile (loads .env.{profile})
    profile: "2023ixf"
    #
    # Option 2: Inline environment variables (self-contained config)
    env:
      REPO: "/path/to/butler/repo"
      STACK_DIR: "/path/to/lsst_stack"
      OBS_NICKEL: "/path/to/obs_nickel"
      RAW_PARENT_DIR: "/path/to/raw/data"

    object: "SN2023ixf"   # Must match target_name in FITS (case-insensitive partial match)
    ra: 210.910833
    dec: 54.316389
    bands: ["r", "i"]

    template:
      type: ps1           # or "coadd"
      degrade_seeing: 2.0  # optional

    nights:
      20230519:
        r: [76482094, 76482095]
        i: [76482096]
      20230521:
        r: []
        i: []

    # Pipeline configuration files (paths relative to obs_nickel/configs/)
    configs:
      science:
        calibrate_image: calibrateImage/tuned_configs/2023ixf_relaxed.py
        calibrate_image_fallbacks:
          - calibrateImage/tuned_configs/2023ixf_relaxed_psfex_sparse.py
        colorterms: apply_colorterms.py
      dia:
        subtract_images: dia/subtractImages.py
        detect_and_measure: dia/detectAndMeasure.py

    options:
      jobs: 8
      skip_calibs: false
      skip_science: false
      skip_dia: false
      forced_phot: true
      forced_phot_image_type: diffim  # visit, diffim, or both
      lightcurve: true
      lightcurve_dataset_type: dia_source_unfiltered  # or forced_phot_diffim_radec
      lightcurve_min_snr: 3.0
      use_fallbacks: true    # Try fallback configs on failure
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config

log = logging.getLogger(__name__)


def _generate_run_id() -> str:
    """Generate a unique run ID for unified logging across Python and shell."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{os.getpid()}"


def _get_step_log_file(step: str, night: str = "", band: str = "") -> Path | None:
    """Get the log file path for a specific pipeline step.

    Uses RUN_LOG_DIR environment variable set by _setup_run_logging.
    Organizes logs into subdirectories by step type:
    - bootstrap/ for bootstrap logs
    - templates/ for PS1 and coadd template logs
    - calibs/ for calibration logs
    - science/ for science processing logs
    - dia/ for difference imaging logs
    - fphot/ for forced photometry logs
    - lightcurve/ for lightcurve extraction logs

    Args:
        step: Pipeline step name (e.g., "bootstrap", "calibs", "science", "dia")
        night: Optional night identifier for per-night steps
        band: Optional band identifier for per-band steps

    Returns:
        Path to log file if RUN_LOG_DIR is set, None otherwise
    """
    run_log_dir = os.environ.get("RUN_LOG_DIR")
    if not run_log_dir:
        return None

    base_dir = Path(run_log_dir)

    # Map step names to subdirectories
    # Template-related steps go into templates/
    if step in ("ps1_template", "coadd_template"):
        step_dir = base_dir / "templates"
        # For templates, use band as the main identifier
        if band:
            log_name = f"{step}_{band}.log"
        else:
            log_name = f"{step}.log"
    # Template night processing goes into separate dirs
    elif step in ("calibs_template", "science_template"):
        base_step = step.replace("_template", "")
        step_dir = base_dir / f"{base_step}_template"
        log_name = f"{night}.log" if night else f"{step}.log"
    # Regular pipeline steps
    elif step == "bootstrap":
        step_dir = base_dir / "bootstrap"
        log_name = "bootstrap.log"
    elif step == "lightcurve":
        step_dir = base_dir / "lightcurve"
        # Support multiple lightcurve extractions (forced phot vs DIA sources)
        # The 'night' parameter is used to distinguish the type
        if night:
            log_name = f"{night}.log"  # e.g., "forced_phot.log" or "dia_sources.log"
        else:
            log_name = "lightcurve.log"
    else:
        # calibs, science, dia, fphot
        step_dir = base_dir / step
        # Build filename from night and band
        parts = []
        if night:
            parts.append(night)
        if band:
            parts.append(band)
        log_name = "_".join(parts) + ".log" if parts else f"{step}.log"

    # Create step directory
    step_dir.mkdir(parents=True, exist_ok=True)

    return step_dir / log_name


def _parse_log_data_id(line: str) -> dict[str, str] | None:
    """Extract dataId from LSST long-log format.

    LSST --long-log format includes dataId in parentheses:
        (cpBiasIsr:{instrument: 'Nickel', detector: 0, exposure: 86008005, ...})

    Returns:
        Dictionary with task_label and dataId fields, or None if not found.
    """
    match = re.search(r"\((\w+):\{([^}]+)\}\)", line)
    if not match:
        return None

    data_id: dict[str, str] = {"task_label": match.group(1)}
    for kv in re.finditer(r"(\w+):\s*('([^']*)'|(\d+)|(\w+))", match.group(2)):
        data_id[kv.group(1)] = kv.group(3) or kv.group(4) or kv.group(5)
    return data_id


def _split_step_logs(run_log_dir: Path) -> None:
    """Split interleaved step log files by exposure for easier reading.

    After a pipeline run, walks all step log directories and splits any log
    file with multiple exposures into per-exposure files within a subdirectory.

    For example:
        calibs/20230519.log  →  calibs/20230519/
                                  _general.log        (ingest, defineVisits, qgraph, etc.)
                                  exp85950225.log     (all tasks for this exposure)
                                  exp85950236.log
                                  exp86203012.log
    """
    step_dirs = [
        "calibs",
        "science",
        "dia",
        "fphot",
        "calibs_template",
        "science_template",
        "templates",
    ]

    for step_name in step_dirs:
        step_dir = run_log_dir / step_name
        if not step_dir.is_dir():
            continue

        for log_file in step_dir.glob("*.log"):
            _split_single_log(log_file)


def _split_single_log(log_file: Path) -> None:
    """Split a single log file by exposure/visit into a subdirectory.

    Each exposure (or visit, for DIA/fphot steps) gets one file containing
    all log lines (across all tasks) for that identifier. Lines without a
    dataId go into _general.log.
    """
    with open(log_file) as f:
        lines = f.readlines()

    grouped: dict[str, list[str]] = defaultdict(list)
    current_exposure = "_general"

    for line in lines:
        data_id = _parse_log_data_id(line)
        if data_id:
            # Calibs use "exposure", DIA/fphot use "visit"
            current_exposure = (
                data_id.get("exposure") or data_id.get("visit") or "_general"
            )
        grouped[current_exposure].append(line)

    # Only split if there are multiple exposures
    real_exposures = [k for k in grouped if k != "_general"]
    if len(real_exposures) <= 1:
        return

    split_dir = log_file.with_suffix("")
    split_dir.mkdir(parents=True, exist_ok=True)

    for exposure, exp_lines in sorted(grouped.items()):
        if exposure == "_general":
            out_path = split_dir / "_general.log"
        else:
            out_path = split_dir / f"exp{exposure}.log"
        with open(out_path, "w") as f:
            f.writelines(exp_lines)

    log.info(
        f"Split {log_file.name} → {split_dir.name}/ "
        f"({len(real_exposures)} exposures + general)"
    )


def _maybe_split_log(log_file: Path | None) -> None:
    """Split a log file by exposure if it exists and has multiple exposures."""
    if log_file and log_file.exists():
        _split_single_log(log_file)


def _setup_run_logging(run_id: str, config: Config) -> Path:
    """Set up unified logging directory for a pipeline run.

    Creates the run log directory and adds a FileHandler so all Python
    log output is captured alongside the shell script logs.

    Also sets RUN_ID in os.environ so child shell scripts (via
    run_with_stack) inherit it and write to the same directory.

    Args:
        run_id: Unique run identifier
        config: Pipeline configuration

    Returns:
        Path to the run log directory
    """
    # Use the same LOG_ROOT as logging.sh: {REPO_ROOT}/logs
    # REPO_ROOT is the monorepo root (obs_nickel.parent.parent)
    repo_root = config.obs_nickel.parent.parent
    log_root = repo_root / "logs"
    run_log_dir = log_root / run_id

    run_log_dir.mkdir(parents=True, exist_ok=True)

    # Set RUN_ID in environment so shell scripts (via run_with_stack)
    # inherit it and their logging.sh uses the same directory
    os.environ["RUN_ID"] = run_id

    # Set RUN_LOG_DIR in environment so child modules can access it
    os.environ["RUN_LOG_DIR"] = str(run_log_dir)

    # Add a file handler for Python-level logs
    pipeline_log = run_log_dir / "pipeline.log"
    file_handler = logging.FileHandler(pipeline_log)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    )

    # Add to root logger so all core modules' logs are captured
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Write run metadata
    run_info = run_log_dir / "run_info.txt"
    with open(run_info, "w") as f:
        f.write(f"Run ID: {run_id}\n")
        f.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Repository: {config.repo}\n")
        f.write(f"Pipeline log: {pipeline_log}\n")
        f.write(f"Log directory: {run_log_dir}\n")
        f.write("")

    return run_log_dir


@dataclass
class ScienceConfigs:
    """Science processing configuration paths."""

    calibrate_image: str | None = None
    calibrate_image_fallbacks: list[str] = field(default_factory=list)
    colorterms: str | None = None


@dataclass
class DIAConfigs:
    """DIA processing configuration paths."""

    subtract_images: str | None = None
    detect_and_measure: str | None = None


@dataclass
class CoaddConfigs:
    """Coadd template building configuration paths."""

    make_direct_warp: str | None = None


@dataclass
class RunConfig:
    """Configuration parsed from YAML."""

    object_name: str
    ra: float
    dec: float
    bands: list[str]
    nights: dict[str, dict[str, list[int]]]

    # Template configuration
    template_type: str = "ps1"  # "ps1" or "coadd"
    template_degrade_seeing: float | None = None
    template_nights: list[str] = field(default_factory=list)

    # Pipeline config files
    science_configs: ScienceConfigs = field(default_factory=ScienceConfigs)
    dia_configs: DIAConfigs = field(default_factory=DIAConfigs)
    coadd_configs: CoaddConfigs = field(default_factory=CoaddConfigs)

    # Processing options
    jobs: int = 8
    skip_calibs: bool = False
    skip_science: bool = False
    skip_dia: bool = False
    forced_phot: bool = True
    forced_phot_image_type: str = "diffim"  # visit, diffim, or both
    lightcurve: bool = True
    lightcurve_dataset_type: str = "dia_source_unfiltered"
    lightcurve_min_snr: float = 3.0
    continue_on_error: bool = True
    use_fallbacks: bool = True

    # Environment profile (optional - embedded in YAML instead of -p flag)
    profile: str | None = None

    @classmethod
    def from_yaml(cls, path: Path) -> RunConfig:
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Extract template config
        template = data.get("template", {})
        template_type = template.get("type", "ps1")
        template_degrade_seeing = template.get("degrade_seeing")
        # Convert template nights to strings (YAML parses 20230519 as int)
        template_nights = [str(n) for n in template.get("nights", [])]

        # Extract options
        options = data.get("options", {})

        # Convert night keys to strings (YAML parses 20230519 as int)
        # Normalize None values to empty dicts (happens when band lines are commented out)
        raw_nights = data.get("nights", {})
        nights = {str(k): (v if v is not None else {}) for k, v in raw_nights.items()}

        # Extract config file paths
        configs = data.get("configs", {})
        science_cfg_data = configs.get("science", {})
        dia_cfg_data = configs.get("dia", {})

        science_configs = ScienceConfigs(
            calibrate_image=science_cfg_data.get("calibrate_image"),
            calibrate_image_fallbacks=science_cfg_data.get(
                "calibrate_image_fallbacks", []
            ),
            colorterms=science_cfg_data.get("colorterms"),
        )

        dia_configs = DIAConfigs(
            subtract_images=dia_cfg_data.get("subtract_images"),
            detect_and_measure=dia_cfg_data.get("detect_and_measure"),
        )

        coadd_cfg_data = configs.get("coadd", {})
        coadd_configs = CoaddConfigs(
            make_direct_warp=coadd_cfg_data.get("make_direct_warp"),
        )

        return cls(
            object_name=data.get("object", ""),
            ra=data["ra"],
            dec=data["dec"],
            bands=data.get("bands", ["r"]),
            nights=nights,
            template_type=template_type,
            template_degrade_seeing=template_degrade_seeing,
            template_nights=template_nights,
            science_configs=science_configs,
            dia_configs=dia_configs,
            coadd_configs=coadd_configs,
            jobs=options.get("jobs", 8),
            skip_calibs=options.get("skip_calibs", False),
            skip_science=options.get("skip_science", False),
            skip_dia=options.get("skip_dia", False),
            forced_phot=options.get("forced_phot", True),
            forced_phot_image_type=options.get("forced_phot_image_type", "diffim"),
            lightcurve=options.get("lightcurve", True),
            lightcurve_dataset_type=options.get(
                "lightcurve_dataset_type", "dia_source_unfiltered"
            ),
            lightcurve_min_snr=float(options.get("lightcurve_min_snr", 3.0)),
            continue_on_error=options.get("continue_on_error", True),
            use_fallbacks=options.get("use_fallbacks", True),
            profile=data.get("profile"),
        )


def get_profile_from_yaml(path: Path) -> str | None:
    """Extract just the profile field from a pipeline YAML file.

    This is a lightweight function to get the profile before loading
    the full environment configuration.

    Args:
        path: Path to pipeline YAML file

    Returns:
        Profile name if specified, None otherwise
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("profile")


def get_env_from_yaml(path: Path) -> dict[str, str] | None:
    """Extract inline environment variables from a pipeline YAML file.

    This allows pipeline configs to be self-contained by embedding
    environment variables directly in the YAML.

    Args:
        path: Path to pipeline YAML file

    Returns:
        Dict of environment variables if 'env' section exists, None otherwise
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    env_section = data.get("env")
    if env_section and isinstance(env_section, dict):
        # Convert all values to strings
        return {str(k): str(v) for k, v in env_section.items()}
    return None


@dataclass
class RunResult:
    """Result of pipeline run."""

    success: bool
    failed_calibs: list[str] = field(default_factory=list)
    failed_science: list[str] = field(default_factory=list)
    failed_dia: list[str] = field(default_factory=list)
    failed_fphot: list[str] = field(default_factory=list)
    template_collections: dict[str, str] = field(default_factory=dict)
    forced_phot_collections: dict[str, list[str]] = field(default_factory=dict)
    lightcurve_path: str | None = None
    log_dir: str | None = None
    error: str | None = None


def run(
    config_file: Path,
    config: Config,
    *,
    dry_run: bool = False,
) -> RunResult:
    """Run full pipeline from YAML configuration.

    This orchestrates:
    0. Bootstrap repository if needed (auto-detected)
    1. PS1 template ingestion (or coadd building) per band
    2. Calibrations per night
    3. Science processing per night
    4. DIA per night per band
    5. Forced photometry per night
    6. Lightcurve extraction

    Args:
        config_file: Path to YAML configuration file
        config: Pipeline configuration
        dry_run: Print commands without executing

    Returns:
        RunResult with status and any failures
    """
    from obs_nickel_data_tools.core import (
        bootstrap,
        calibs,
        coadd,
        dia,
        fphot,
        lightcurve,
        ps1_template,
        science,
    )
    from obs_nickel_data_tools.core.science import ScienceConfig
    from obs_nickel_data_tools.core.stack import run_butler

    # Set up unified logging directory for this pipeline run
    # All Python logs and shell script logs go under the same RUN_ID
    run_id = _generate_run_id()
    run_log_dir = _setup_run_logging(run_id, config)
    log.info(f"Logs: {run_log_dir}")

    # Step 0: Check if bootstrap is needed
    if bootstrap.needs_bootstrap(config):
        log.info(f"Repository not initialized, running bootstrap: {config.repo}")
        if not dry_run:
            bootstrap_log = _get_step_log_file("bootstrap")
            bootstrap_result = bootstrap.run(config, log_file=bootstrap_log)
            if not bootstrap_result.success:
                return RunResult(
                    success=False,
                    error=f"Bootstrap failed: {bootstrap_result.error}",
                    log_dir=str(run_log_dir),
                )
            log.info("Bootstrap complete")
        else:
            log.info("[DRY RUN] Would run bootstrap")

    # Load run configuration
    run_cfg = RunConfig.from_yaml(config_file)

    # Build ScienceConfig from YAML paths
    configs_dir = config.obs_nickel / "configs"
    science_cfg = ScienceConfig.default(config.obs_nickel)

    # Override with YAML-specified configs if present
    if run_cfg.science_configs.calibrate_image:
        science_cfg.calibrate_image = (
            configs_dir / run_cfg.science_configs.calibrate_image
        )
    if run_cfg.science_configs.colorterms:
        science_cfg.colorterms = configs_dir / run_cfg.science_configs.colorterms
    if run_cfg.science_configs.calibrate_image_fallbacks:
        science_cfg.calibrate_image_fallbacks = [
            configs_dir / fb for fb in run_cfg.science_configs.calibrate_image_fallbacks
        ]

    result = RunResult(success=True, log_dir=str(run_log_dir))
    all_nights = list(run_cfg.nights.keys())

    log.info(f"Pipeline run for {run_cfg.object_name}")
    log.info(f"  Target: RA={run_cfg.ra:.4f}, Dec={run_cfg.dec:.4f}")
    log.info(f"  Bands: {run_cfg.bands}")
    log.info(f"  Template type: {run_cfg.template_type}")
    log.info(f"  Nights: {len(all_nights)}")
    if run_cfg.template_type == "coadd" and run_cfg.template_nights:
        log.info(f"  Template nights: {run_cfg.template_nights}")

    if dry_run:
        log.info("[DRY RUN] Commands would be executed:")

    # Step 1: Templates per band
    if run_cfg.template_type == "ps1":
        # PS1 templates (r/i bands only)
        for band in run_cfg.bands:
            if band not in ("r", "i"):
                log.warning(f"PS1 templates not available for band {band}, skipping")
                continue

            log.info(f"Ingesting PS1 template for {band}-band...")

            if not dry_run:
                ps1_log = _get_step_log_file("ps1_template", band=band)
                ps1_result = ps1_template.run(
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    band=band,
                    config=config,
                    degrade_seeing=run_cfg.template_degrade_seeing,
                    log_file=ps1_log,
                )
                if ps1_result.success:
                    result.template_collections[band] = ps1_result.collection
                else:
                    log.warning(f"PS1 template failed for {band}: {ps1_result.error}")
            else:
                log.info(
                    f"  [DRY RUN] ps1_template.run(ra={run_cfg.ra}, dec={run_cfg.dec}, band={band})"
                )
                result.template_collections[band] = f"templates/ps1/{band}"

        # Log template summary
        built = [b for b in run_cfg.bands if b in result.template_collections]
        failed = [b for b in run_cfg.bands if b not in result.template_collections]
        if built:
            log.info(f"Templates built for bands: {', '.join(built)}")
        if failed:
            log.warning(
                f"No templates for bands: {', '.join(failed)} (DIA will be skipped for these)"
            )

    elif run_cfg.template_type == "coadd":
        # Nickel coadd templates - requires processing template nights first
        if not run_cfg.template_nights:
            log.error("Coadd template type requires template.nights in YAML")
            return RunResult(
                success=False,
                error="Coadd template type requires template.nights configuration",
            )

        # Step 1a: Process template nights through calibs and science
        log.info("Processing template nights...")
        template_nights_to_process = run_cfg.template_nights

        if not run_cfg.skip_calibs:
            for night in template_nights_to_process:
                log.info(f"Running calibrations for template night {night}...")
                if not dry_run:
                    calib_log = _get_step_log_file("calibs_template", night=night)
                    calib_result = calibs.run(
                        night, config, jobs=run_cfg.jobs, log_file=calib_log
                    )
                    _maybe_split_log(calib_log)
                    if not calib_result.success:
                        log.warning(
                            f"Calibrations failed for template night {night}: {calib_result.error}"
                        )
                        if not run_cfg.continue_on_error:
                            return RunResult(
                                success=False,
                                error=f"Template night calibrations failed for {night}",
                            )
                else:
                    log.info(f"  [DRY RUN] calibs.run({night})")

        if not run_cfg.skip_science:
            for night in template_nights_to_process:
                log.info(f"Running science for template night {night}...")
                if not dry_run:
                    sci_log = _get_step_log_file("science_template", night=night)
                    sci_result = science.run(
                        night,
                        config,
                        jobs=run_cfg.jobs,
                        object_filter=run_cfg.object_name,
                        skip_coadds=True,
                        science_cfg=science_cfg,
                        use_fallbacks=run_cfg.use_fallbacks,
                        log_file=sci_log,
                    )
                    _maybe_split_log(sci_log)
                    if not sci_result.success:
                        log.warning(
                            f"Science failed for template night {night}: {sci_result.error}"
                        )
                        if not run_cfg.continue_on_error:
                            return RunResult(
                                success=False,
                                error=f"Template night science failed for {night}",
                            )
                else:
                    log.info(f"  [DRY RUN] science.run({night})")

        # Step 1b: Build coadd templates per band
        for band in run_cfg.bands:
            log.info(f"Building coadd template for {band}-band...")

            if not dry_run:
                # Build config file list for pipetask -C
                coadd_config_files = []
                if run_cfg.coadd_configs.make_direct_warp:
                    cfg_path = (
                        config.obs_nickel
                        / "configs"
                        / run_cfg.coadd_configs.make_direct_warp
                    )
                    coadd_config_files.append(f"makeDirectWarp:{cfg_path}")

                coadd_log = _get_step_log_file("coadd_template", band=band)
                coadd_result = coadd.run(
                    nights=run_cfg.template_nights,
                    band=band,
                    config=config,
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    jobs=run_cfg.jobs,
                    config_files=coadd_config_files or None,
                    log_file=coadd_log,
                )
                _maybe_split_log(coadd_log)
                if coadd_result.success:
                    result.template_collections[band] = coadd_result.collection
                    log.info(f"  Coadd template for {band}: {coadd_result.collection}")
                else:
                    log.warning(
                        f"Coadd template failed for {band}: {coadd_result.error}"
                    )
            else:
                log.info(
                    f"  [DRY RUN] coadd.run(nights={run_cfg.template_nights}, band={band})"
                )
                result.template_collections[band] = f"templates/deep/tract0/{band}"

        # Log template summary
        built = [b for b in run_cfg.bands if b in result.template_collections]
        failed = [b for b in run_cfg.bands if b not in result.template_collections]
        if built:
            log.info(f"Templates built for bands: {', '.join(built)}")
        if failed:
            log.warning(
                f"No templates for bands: {', '.join(failed)} (DIA will be skipped for these)"
            )

    # Step 2: Calibrations per night
    if not run_cfg.skip_calibs:
        for night in all_nights:
            log.info(f"Running calibrations for {night}...")

            if not dry_run:
                calib_log = _get_step_log_file("calibs", night=night)
                calib_result = calibs.run(
                    night, config, jobs=run_cfg.jobs, log_file=calib_log
                )
                _maybe_split_log(calib_log)
                if not calib_result.success:
                    result.failed_calibs.append(night)
                    log.warning(
                        f"Calibrations failed for {night}: {calib_result.error}"
                    )
                    if not run_cfg.continue_on_error:
                        result.success = False
                        result.error = f"Calibrations failed for {night}"
                        return result
            else:
                log.info(f"  [DRY RUN] calibs.run({night})")

    # Step 3: Science per night
    if not run_cfg.skip_science:
        for night in all_nights:
            log.info(f"Running science for {night}...")

            if not dry_run:
                sci_log = _get_step_log_file("science", night=night)
                sci_result = science.run(
                    night,
                    config,
                    jobs=run_cfg.jobs,
                    object_filter=run_cfg.object_name,
                    skip_coadds=True,
                    science_cfg=science_cfg,
                    use_fallbacks=run_cfg.use_fallbacks,
                    target_ra=run_cfg.ra,
                    target_dec=run_cfg.dec,
                    log_file=sci_log,
                )
                _maybe_split_log(sci_log)
                if not sci_result.success:
                    result.failed_science.append(night)
                    log.warning(f"Science failed for {night}: {sci_result.error}")
                    if not run_cfg.continue_on_error:
                        result.success = False
                        result.error = f"Science failed for {night}"
                        return result
                elif sci_result.fallback_used:
                    log.info(
                        f"  Note: {night} used fallback config: {sci_result.config_used}"
                    )
            else:
                log.info(f"  [DRY RUN] science.run({night})")

    # Step 4: DIA per night per band
    if not run_cfg.skip_dia:
        for night in all_nights:
            night_bands = run_cfg.nights.get(night, {})

            # Determine which bands to process for this night.
            # If the night has explicit band keys, only run those bands.
            # If the night has no band keys (empty dict), run all top-level bands.
            if night_bands:
                bands_for_night = [b for b in run_cfg.bands if b in night_bands]
            else:
                bands_for_night = list(run_cfg.bands)

            if not bands_for_night:
                log.info(f"Skipping DIA for {night} (no bands configured)")
                continue

            for band in bands_for_night:
                # Check if we have a template for this band
                template_coll = result.template_collections.get(band)
                if template_coll is None:
                    log.warning(
                        f"Skipping DIA for {night}/{band} (no template available)"
                    )
                    result.failed_dia.append(f"{night}/{band}")
                    continue

                log.info(f"Running DIA for {night}/{band}...")

                if not dry_run:
                    dia_log = _get_step_log_file("dia", night=night, band=band)
                    dia_result = dia.run(
                        night,
                        config,
                        jobs=run_cfg.jobs,
                        template=template_coll,
                        auto_template=False,  # We have explicit template
                        prefer_ps1=run_cfg.template_type == "ps1",
                        band=band,
                        object_filter=run_cfg.object_name,
                        log_file=dia_log,
                    )
                    _maybe_split_log(dia_log)
                    if not dia_result.success:
                        result.failed_dia.append(f"{night}/{band}")
                        log.warning(
                            f"DIA failed for {night}/{band}: {dia_result.error}"
                        )
                        if not run_cfg.continue_on_error:
                            result.success = False
                            result.error = f"DIA failed for {night}/{band}"
                            return result
                else:
                    log.info(f"  [DRY RUN] dia.run({night}, band={band})")

    # Step 5: Forced photometry per night
    failed_dia_set = set(result.failed_dia)
    if run_cfg.forced_phot:
        for night in all_nights:
            # Skip fphot for nights where ALL DIA bands failed (no diff images to measure)
            night_bands = run_cfg.nights.get(night, {})
            if night_bands:
                bands_for_night = [b for b in run_cfg.bands if b in night_bands]
            else:
                bands_for_night = list(run_cfg.bands)
            all_dia_failed = all(
                f"{night}/{b}" in failed_dia_set for b in bands_for_night
            )
            if all_dia_failed and bands_for_night:
                log.info(
                    f"Skipping forced photometry for {night} (all DIA bands failed)"
                )
                result.failed_fphot.append(night)
                continue

            log.info(f"Running forced photometry for {night}...")

            if not dry_run:
                fphot_log = _get_step_log_file("fphot", night=night)
                fphot_result = fphot.run(
                    night=night,
                    ra=run_cfg.ra,
                    dec=run_cfg.dec,
                    config=config,
                    image_type=run_cfg.forced_phot_image_type,
                    log_file=fphot_log,
                )
                _maybe_split_log(fphot_log)
                if not fphot_result.success:
                    result.failed_fphot.append(night)
                    log.warning(f"Forced phot failed for {night}: {fphot_result.error}")
                else:
                    result.forced_phot_collections[night] = (
                        fphot_result.output_collections
                    )
            else:
                log.info(
                    f"  [DRY RUN] fphot.run({night}, image_type={run_cfg.forced_phot_image_type})"
                )

    # Step 6: Lightcurve extraction
    if run_cfg.lightcurve:
        log.info("Extracting lightcurve...")

        use_forced_phot = run_cfg.lightcurve_dataset_type.startswith("forced_phot")

        if use_forced_phot:
            # Build collection list from forced photometry outputs
            fphot_colls: list[str] = []
            for night in all_nights:
                colls = result.forced_phot_collections.get(night, [])
                if colls:
                    fphot_colls.extend(colls)

            # If no forced phot ran this session (e.g. forced_phot: false),
            # discover existing collections from the Butler
            if not fphot_colls and not dry_run:
                log.info("No forced phot from this run, discovering from Butler...")
                # Determine collection suffix from image_type
                fphot_suffix = run_cfg.forced_phot_image_type
                for night in all_nights:
                    try:
                        check_result = run_butler(
                            [
                                "query-collections",
                                str(config.repo),
                                f"Nickel/runs/{night}/forcedPhotRaDec/*/{fphot_suffix}*",
                            ],
                            config,
                            capture_output=True,
                            check=False,
                        )
                        if check_result.returncode == 0:
                            for line in check_result.stdout.strip().splitlines():
                                parts = line.strip().split()
                                if parts and parts[0].startswith("Nickel/runs/"):
                                    fphot_colls.append(parts[0])
                    except Exception:
                        pass
            elif not fphot_colls and dry_run:
                for night in all_nights:
                    fphot_colls.append(f"Nickel/runs/{night}/forcedPhotRaDec/*/run")

            if not fphot_colls:
                log.warning(
                    "No forced photometry collections found, skipping lightcurve extraction"
                )
            else:
                collections = ",".join(sorted(set(fphot_colls)))
                log.info(
                    f"Lightcurve using {len(set(fphot_colls))} forced phot collections"
                )

                if not dry_run:
                    lc_log = _get_step_log_file("lightcurve", night="forced_phot")
                    lc_result = lightcurve.run(
                        ra=run_cfg.ra,
                        dec=run_cfg.dec,
                        collections=collections,
                        config=config,
                        name=run_cfg.object_name,
                        plot=True,
                        min_snr=run_cfg.lightcurve_min_snr,
                        dataset_type=run_cfg.lightcurve_dataset_type,
                        log_file=lc_log,
                    )
                    if lc_result.success:
                        result.lightcurve_path = lc_result.csv_path
                    else:
                        log.warning(f"Lightcurve extraction failed: {lc_result.error}")
                else:
                    log.info("  [DRY RUN] lightcurve.run()")
        else:
            # Build collection list from nights that actually have diff collections
            # in the Butler (not just nights where DIA was "attempted")
            verified_collections: list[str] = []
            failed_night_bands = set(result.failed_dia)
            for night in all_nights:
                # Skip nights where all bands failed DIA
                night_bands = run_cfg.nights.get(night, {})
                if night_bands:
                    bands_for_night = [b for b in run_cfg.bands if b in night_bands]
                else:
                    bands_for_night = list(run_cfg.bands)
                has_success = any(
                    f"{night}/{b}" not in failed_night_bands for b in bands_for_night
                )
                if not has_success:
                    continue

                # Verify the diff collection actually exists in the Butler
                if not dry_run:
                    try:
                        check_result = run_butler(
                            [
                                "query-collections",
                                str(config.repo),
                                f"Nickel/runs/{night}/diff/*/run",
                            ],
                            config,
                            capture_output=True,
                            check=False,
                        )
                        if check_result.returncode == 0:
                            for line in check_result.stdout.strip().splitlines():
                                # butler query-collections outputs "name TYPE"
                                # e.g. "Nickel/runs/.../run RUN" — take first column only
                                parts = line.strip().split()
                                if parts and parts[0].startswith("Nickel/runs/"):
                                    verified_collections.append(parts[0])
                    except Exception:
                        log.debug(f"Could not verify diff collection for {night}")
                else:
                    verified_collections.append(f"Nickel/runs/{night}/diff/*/run")

            if not verified_collections:
                log.warning(
                    "No nights with verified DIA collections, skipping lightcurve extraction"
                )
            else:
                collections = ",".join(verified_collections)
                log.info(
                    f"Lightcurve using {len(verified_collections)} diff collections"
                )

                if not dry_run:
                    lc_log = _get_step_log_file("lightcurve", night="dia_sources")
                    lc_result = lightcurve.run(
                        ra=run_cfg.ra,
                        dec=run_cfg.dec,
                        collections=collections,
                        config=config,
                        name=run_cfg.object_name,
                        plot=True,
                        min_snr=run_cfg.lightcurve_min_snr,
                        dataset_type=run_cfg.lightcurve_dataset_type,
                        log_file=lc_log,
                    )
                    if lc_result.success:
                        result.lightcurve_path = lc_result.csv_path
                    else:
                        log.warning(f"Lightcurve extraction failed: {lc_result.error}")
                else:
                    log.info("  [DRY RUN] lightcurve.run()")

    # Determine overall success
    # Use a three-tier status: SUCCESS (no failures), PARTIAL (some failures but
    # usable results like lightcurves or successful nights), FAILED (nothing worked)
    has_failures = bool(
        result.failed_calibs or result.failed_science or result.failed_dia
    )
    has_successes = False

    if has_failures:
        # Check if we got any usable results despite failures
        total_nights = len(all_nights)
        successful_science = total_nights - len(result.failed_science)
        successful_dia_pairs = sum(
            1
            for night in all_nights
            for b in (
                run_cfg.bands
                if not run_cfg.nights.get(night, {})
                else [b for b in run_cfg.bands if b in run_cfg.nights.get(night, {})]
            )
            if f"{night}/{b}" not in set(result.failed_dia)
        )
        successful_fphot = total_nights - len(result.failed_fphot)

        has_successes = (
            successful_science > 0
            or successful_dia_pairs > 0
            or successful_fphot > 0
            or result.lightcurve_path is not None
        )

        if has_successes:
            result.success = True  # Partial success is still success
        else:
            result.success = False

        failures = []
        if result.failed_calibs:
            failures.append(f"calibs: {result.failed_calibs}")
        if result.failed_science:
            failures.append(f"science: {result.failed_science}")
        if result.failed_dia:
            failures.append(f"dia: {result.failed_dia}")
        result.error = "; ".join(failures)

    # Post-process: split any remaining unsplit logs by exposure
    if not dry_run:
        _split_step_logs(run_log_dir)

    # Write summary and log final location
    if not has_failures:
        status = "SUCCESS"
    elif has_successes:
        status = "PARTIAL SUCCESS"
    else:
        status = "FAILED"
    log.info(f"Pipeline {status}")
    log.info(f"All logs: {run_log_dir}")

    # Log success/failure counts
    total_nights = len(all_nights)
    n_calibs_ok = total_nights - len(result.failed_calibs)
    n_science_ok = total_nights - len(result.failed_science)
    n_fphot_ok = total_nights - len(result.failed_fphot)
    total_dia_pairs = sum(
        len(
            run_cfg.bands
            if not run_cfg.nights.get(night, {})
            else [b for b in run_cfg.bands if b in run_cfg.nights.get(night, {})]
        )
        for night in all_nights
    )
    n_dia_ok = total_dia_pairs - len(result.failed_dia)
    log.info(
        f"  Calibs: {n_calibs_ok}/{total_nights}, Science: {n_science_ok}/{total_nights}, "
        f"DIA: {n_dia_ok}/{total_dia_pairs}, Fphot: {n_fphot_ok}/{total_nights}"
    )
    if result.lightcurve_path:
        log.info(f"  Lightcurve: {result.lightcurve_path}")

    summary_file = run_log_dir / "summary.txt"
    with open(summary_file, "w") as f:
        f.write(f"Status: {status}\n")
        f.write(f"Object: {run_cfg.object_name}\n")
        f.write(f"Bands: {run_cfg.bands}\n")
        f.write(f"Nights: {total_nights}\n")
        f.write(f"Calibs OK: {n_calibs_ok}/{total_nights}\n")
        f.write(f"Science OK: {n_science_ok}/{total_nights}\n")
        f.write(f"DIA OK: {n_dia_ok}/{total_dia_pairs}\n")
        f.write(f"Fphot OK: {n_fphot_ok}/{total_nights}\n")
        if result.failed_calibs:
            f.write(f"Failed calibs: {result.failed_calibs}\n")
        if result.failed_science:
            f.write(f"Failed science: {result.failed_science}\n")
        if result.failed_dia:
            f.write(f"Failed DIA: {result.failed_dia}\n")
        if result.failed_fphot:
            f.write(f"Failed fphot: {result.failed_fphot}\n")
        if result.template_collections:
            f.write(f"Templates: {result.template_collections}\n")
        if result.lightcurve_path:
            f.write(f"Lightcurve: {result.lightcurve_path}\n")

    return result
