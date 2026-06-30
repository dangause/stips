"""FITS image rendering for the dashboard.

Renders FITS images to PNG via Butler + astropy/matplotlib subprocess.
Results cached as PNGs in a temp directory.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache directory for rendered PNGs
_CACHE_DIR = Path(tempfile.gettempdir()) / "stips-dashboard-cache"


def get_cache_dir() -> Path:
    """Return the cache directory, creating it if needed."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def get_cached_png(
    run_id: str, dataset_type: str, night: str, band: str
) -> Path | None:
    """Return path to cached PNG if it exists."""
    png_path = _png_path(run_id, dataset_type, night, band)
    return png_path if png_path.exists() else None


def render_fits_image(
    repo_path: str,
    run_id: str,
    dataset_type: str,
    night: str,
    band: str,
    instrument_name: str = "Nickel",
) -> Path | None:
    """Render a FITS image from Butler to a cached PNG file.

    Returns path to the PNG file, or None if rendering failed.
    """
    png_path = _png_path(run_id, dataset_type, night, band)
    if png_path.exists():
        return png_path

    png_path.parent.mkdir(parents=True, exist_ok=True)

    script = _build_render_script(
        repo_path, dataset_type, night, band, str(png_path), instrument_name
    )

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "FITS render failed for %s/%s/%s: %s",
                night,
                band,
                dataset_type,
                result.stderr[:500],
            )
            return None

        if png_path.exists():
            return png_path
        return None

    except subprocess.TimeoutExpired:
        logger.warning("FITS render timed out for %s/%s/%s", night, band, dataset_type)
        return None
    except Exception as e:
        logger.warning("FITS render error: %s", e)
        return None


def list_available_images(repo_path: str) -> list[dict]:
    """Query Butler for available (night, band, dataset_type) combinations.

    Returns list of dicts with keys: night, band, dataset_type.
    """
    script = _build_list_script(repo_path)

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("FITS list query failed: %s", result.stderr[:500])
            return []

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("FITS list error: %s", e)
        return []


def _png_path(run_id: str, dataset_type: str, night: str, band: str) -> Path:
    """Construct the cache path for a rendered PNG."""
    safe_dt = dataset_type.replace("/", "_")
    return get_cache_dir() / run_id / f"{night}_{band}_{safe_dt}.png"


def _build_render_script(
    repo_path: str,
    dataset_type: str,
    night: str,
    band: str,
    output_path: str,
    instrument_name: str = "Nickel",
) -> str:
    """Build Python script that loads FITS via Butler and renders to PNG."""
    return f"""
import sys
try:
    from lsst.daf.butler import Butler
    import numpy as np
    from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"Missing dependency: {{e}}", file=sys.stderr)
    sys.exit(1)

repo = "{repo_path}"
dataset_type = "{dataset_type}"
night = "{night}"
band = "{band}"
output = "{output_path}"

try:
    butler = Butler(repo)
    # Find matching datasets
    refs = list(butler.registry.queryDatasets(
        dataset_type,
        where="instrument=\\'{instrument_name}\\' AND day_obs={{night_int}} AND band=\\'{{band_val}}\\'".format(
            night_int=int(night), band_val=band
        ),
    ))

    if not refs:
        # Try without band constraint for template types
        refs = list(butler.registry.queryDatasets(
            dataset_type,
            where="instrument=\\'{instrument_name}\\' AND day_obs={{night_int}}".format(night_int=int(night)),
        ))

    if not refs:
        print(f"No {{dataset_type}} found for {{night}}/{{band}}", file=sys.stderr)
        sys.exit(1)

    # Use first matching ref
    exposure = butler.get(refs[0])

    # Get the image array
    if hasattr(exposure, "image"):
        img_data = exposure.image.array
    elif hasattr(exposure, "getImage"):
        img_data = exposure.getImage().array
    else:
        img_data = np.asarray(exposure)

    # Apply ZScale + Asinh stretch
    interval = ZScaleInterval()
    stretch = AsinhStretch(a=0.1)
    norm = ImageNormalize(img_data, interval=interval, stretch=stretch)

    fig, ax = plt.subplots(1, 1, figsize=(8, 8), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    ax.imshow(img_data, norm=norm, cmap="gray", origin="lower")
    ax.set_title(f"{{dataset_type}} | {{night}} | {{band}}", color="#e6edf3", fontsize=10)
    ax.tick_params(colors="#8b949e", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#30363d")
    fig.tight_layout(pad=1.0)
    fig.savefig(output, dpi=100, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("OK")

except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""


def _build_list_script(repo_path: str) -> str:
    """Build Python script that lists available image datasets."""
    return f"""
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print("[]")
    sys.exit(0)

repo = "{repo_path}"
dataset_types = ["calexp", "goodSeeingDiff_differenceExp", "goodSeeingDiff_templateExp"]

try:
    butler = Butler(repo)
    results = []
    seen = set()

    for dt in dataset_types:
        try:
            refs = list(butler.registry.queryDatasets(dt))
            for ref in refs:
                did = ref.dataId
                night = str(did.get("day_obs", ""))[:8]
                band = did.get("band", did.get("physical_filter", "?"))
                key = f"{{night}}_{{band}}_{{dt}}"
                if key not in seen:
                    seen.add(key)
                    results.append({{"night": night, "band": band, "dataset_type": dt}})
        except Exception:
            pass

    print(json.dumps(results))
except Exception as e:
    print("[]")
    sys.exit(0)
"""
