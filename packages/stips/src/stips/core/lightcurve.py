"""Lightcurve extraction from DIA source catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core.stack import run_with_stack

if TYPE_CHECKING:
    from stips.core.config import Config


@dataclass
class LightcurveConfig:
    """Configuration for lightcurve extraction and plotting."""

    enabled: bool = True

    # Data selection
    dataset_type: str = "dia_source_unfiltered"
    min_snr: float = 3.0
    max_mag_err: float | None = None
    radius: float = 1.0
    band: str | None = None

    # Y-axis display
    y_axis: str = "apparent_mag"  # apparent_mag | absolute_mag | flux_nJy | flux_adu
    distance_modulus: float | None = None

    # X-axis display
    x_axis: str = "mjd"  # mjd | days_since_explosion
    explosion_mjd: float | None = None

    _VALID_Y_AXES = ("apparent_mag", "absolute_mag", "flux_nJy", "flux_adu")
    _VALID_X_AXES = ("mjd", "days_since_explosion")

    def validate(self):
        """Raise ValueError if config is inconsistent."""
        if self.y_axis not in self._VALID_Y_AXES:
            raise ValueError(
                f"Invalid y_axis '{self.y_axis}', must be one of: {self._VALID_Y_AXES}"
            )
        if self.x_axis not in self._VALID_X_AXES:
            raise ValueError(
                f"Invalid x_axis '{self.x_axis}', must be one of: {self._VALID_X_AXES}"
            )
        if self.y_axis == "absolute_mag" and self.distance_modulus is None:
            raise ValueError(
                "y_axis='absolute_mag' requires distance_modulus to be set"
            )
        if self.x_axis == "days_since_explosion" and self.explosion_mjd is None:
            raise ValueError(
                "x_axis='days_since_explosion' requires explosion_mjd to be set"
            )

    @classmethod
    def from_yaml(
        cls, lc_section: dict | None, options: dict | None = None
    ) -> "LightcurveConfig":
        """Parse from YAML lightcurve: section with fallback to options: block.

        Args:
            lc_section: The 'lightcurve:' top-level YAML dict (may be None).
            options: The 'options:' YAML dict for backwards compat (may be None).

        Returns:
            Validated LightcurveConfig instance.
        """
        lc = lc_section or {}
        opts = options or {}

        config = cls(
            enabled=lc.get("enabled", opts.get("lightcurve", True)),
            dataset_type=lc.get(
                "dataset_type",
                opts.get("lightcurve_dataset_type", "dia_source_unfiltered"),
            ),
            min_snr=float(lc.get("min_snr", opts.get("lightcurve_min_snr", 3.0))),
            max_mag_err=(
                float(lc["max_mag_err"]) if lc.get("max_mag_err") is not None else None
            ),
            radius=float(lc.get("radius", 1.0)),
            band=lc.get("band"),
            y_axis=lc.get("y_axis", "apparent_mag"),
            distance_modulus=(
                float(lc["distance_modulus"])
                if lc.get("distance_modulus") is not None
                else None
            ),
            x_axis=lc.get("x_axis", "mjd"),
            explosion_mjd=(
                float(lc["explosion_mjd"])
                if lc.get("explosion_mjd") is not None
                else None
            ),
        )
        config.validate()
        return config


@dataclass
class LightcurveResult:
    """Result of lightcurve extraction."""

    success: bool
    n_detections: int = 0
    csv_path: str | None = None
    plot_path: str | None = None
    error: str | None = None


def run(
    ra: float,
    dec: float,
    collections: str,
    config: Config,
    *,
    radius: float = 1.0,
    min_snr: float = 3.0,
    band: str | None = None,
    name: str | None = None,
    output: Path | None = None,
    plot: bool = True,
    dataset_type: str = "dia_source_unfiltered",
    log_file: Path | None = None,
    lc_config: LightcurveConfig | None = None,
) -> LightcurveResult:
    """Extract lightcurve from DIA source catalogs or forced photometry.

    Queries source catalogs for detections near the specified coordinates
    and generates a lightcurve CSV and optional plot.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        collections: Comma-separated collection patterns to search
        config: Pipeline configuration
        radius: Match radius in arcseconds (default: 1.0)
        min_snr: Minimum S/N filter (default: 3.0)
        band: Restrict to single band (default: all)
        name: Target name for plot title
        output: Output CSV file path
        plot: Generate plot (default: True)
        dataset_type: Dataset type to query (default: dia_source_unfiltered)
        log_file: Optional path to write LSST pipeline logs

    Returns:
        LightcurveResult with output paths and statistics
    """
    # Set default output path in Butler repo under lightcurves/
    if output is None:
        name_part = name.replace(" ", "_") if name else f"ra{ra:.4f}_dec{dec:.4f}"
        lightcurve_dir = config.repo / "lightcurves"
        lightcurve_dir.mkdir(parents=True, exist_ok=True)
        output = lightcurve_dir / f"lightcurve_{name_part}.csv"
    else:
        # If output is relative, make it relative to repo/lightcurves
        if not output.is_absolute():
            lightcurve_dir = config.repo / "lightcurves"
            lightcurve_dir.mkdir(parents=True, exist_ok=True)
            output = lightcurve_dir / output

    # Build arguments for the extract_lightcurve script
    # Use direct path instead of python -m to avoid PYTHONPATH issues
    # in the LSST stack environment
    script_path = (
        Path(__file__).parent.parent / "pipeline_tools" / "extract_lightcurve.py"
    )
    args = [
        "python",
        str(script_path),
        "--repo",
        str(config.repo),
        "--collection",
        collections,
        "--ra",
        str(ra),
        "--dec",
        str(dec),
        "--radius",
        str(radius),
        "--min-snr",
        str(min_snr),
        "--output",
        str(output),
    ]

    if band:
        args.extend(["--band", band])

    if name:
        args.extend(["--name", name])

    if dataset_type != "dia_source_unfiltered":
        args.extend(["--dataset-type", dataset_type])

    # Display configuration (new lightcurve config options)
    if lc_config:
        args.extend(["--y-axis", lc_config.y_axis])
        args.extend(["--x-axis", lc_config.x_axis])
        if lc_config.explosion_mjd is not None:
            args.extend(["--explosion-mjd", str(lc_config.explosion_mjd)])
        if lc_config.distance_modulus is not None:
            args.extend(["--distance-modulus", str(lc_config.distance_modulus)])
        if lc_config.max_mag_err is not None:
            args.extend(["--max-mag-err", str(lc_config.max_mag_err)])

    if plot:
        args.append("--plot")

    try:
        result = run_with_stack(args, config, capture_output=True, check=False)

        # Write captured output to log file if provided
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "w") as f:
                if result.stdout:
                    f.write(result.stdout)
                if result.stderr:
                    f.write(result.stderr)

        if result.returncode == 0:
            # Parse output to get detection count
            n_detections = 0
            for line in result.stdout.split("\n"):
                if "Total detections:" in line:
                    try:
                        n_detections = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass

            # Check for output files (use absolute paths)
            csv_path = str(output) if output.exists() else None
            plot_path = None
            if plot:
                plot_file = output.parent / f"{output.stem}.png"
                if plot_file.exists():
                    plot_path = str(plot_file)

            return LightcurveResult(
                success=True,
                n_detections=n_detections,
                csv_path=csv_path,
                plot_path=plot_path,
            )
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            # Check for "no detections" which is a common case
            if "No detections found" in error_msg:
                return LightcurveResult(
                    success=False,
                    n_detections=0,
                    error="No detections found matching criteria",
                )
            return LightcurveResult(
                success=False,
                error=error_msg,
            )

    except Exception as e:
        return LightcurveResult(
            success=False,
            error=str(e),
        )
