"""FITS image rendering for the dashboard.

Renders FITS images to PNG via Butler + astropy/matplotlib **inside the
activated LSST stack** (``stips.core.stack.run_butler_python``), replacing the
old bare ``python3 -c`` subprocess path that missed stack activation and queried
stale dataset types (``calexp`` / ``goodSeeingDiff_*``) — finding F-023.
Results are cached as PNGs in a temp directory.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from stips.core.stack import run_butler_python, run_butler_python_json

from .queries import IMAGE_DATASET_TYPES, _preamble, _query_refs_helper, repo_config

if TYPE_CHECKING:
    from stips.core.config import Config

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
    config: "Config | None",
    repo_path: str,
    run_id: str,
    dataset_type: str,
    night: str,
    band: str,
    instrument_name: str,
) -> Path | None:
    """Render a FITS image from Butler to a cached PNG file.

    Returns path to the PNG file, or None if rendering failed (including when
    no stack Config is available — i.e. the dashboard was launched without
    ``-c``).
    """
    if config is None:
        logger.warning("FITS render skipped: no stack configuration")
        return None

    png_path = _png_path(run_id, dataset_type, night, band)
    if png_path.exists():
        return png_path

    png_path.parent.mkdir(parents=True, exist_ok=True)

    script = _build_render_script(
        repo_path, dataset_type, night, band, str(png_path), instrument_name
    )
    run_butler_python(script, repo_config(config, repo_path))

    if png_path.exists():
        return png_path
    logger.warning("FITS render failed for %s/%s/%s", night, band, dataset_type)
    return None


def list_available_images(config: "Config | None", repo_path: str) -> list[dict]:
    """Query Butler for available (night, band, dataset_type) combinations.

    Returns list of dicts with keys: night, band, dataset_type. Uses the
    CURRENT image dataset-type names (``queries.IMAGE_DATASET_TYPES``).
    """
    if config is None:
        return []

    script = _build_list_script(repo_path)
    result = run_butler_python_json(script, repo_config(config, repo_path))
    if not isinstance(result, list):
        return []
    return [r for r in result if isinstance(r, dict)]


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
    instrument_name: str,
) -> str:
    """In-stack snippet that loads a FITS image via Butler and renders a PNG.

    Success is signalled by the PNG appearing at ``output_path`` (the caller
    checks for the file), not by parsing stdout.
    """
    where = f"instrument='{instrument_name}' AND day_obs={int(night)} AND band='{band}'"
    where_no_band = f"instrument='{instrument_name}' AND day_obs={int(night)}"
    return (
        _preamble(repo_path)
        + _query_refs_helper()
        + f"""
import numpy as np
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

dataset_type = {dataset_type!r}
night = {night!r}
band = {band!r}
output = {output_path!r}

refs = _query_refs(dataset_type, {where!r})
if not refs:
    # Try without band constraint for template types
    refs = _query_refs(dataset_type, {where_no_band!r})
if not refs:
    print(f"No {{dataset_type}} found for {{night}}/{{band}}", file=sys.stderr)
    sys.exit(1)

exposure = butler.get(refs[0])

if hasattr(exposure, "image"):
    img_data = exposure.image.array
elif hasattr(exposure, "getImage"):
    img_data = exposure.getImage().array
else:
    img_data = np.asarray(exposure)

interval = ZScaleInterval()
stretch = AsinhStretch(a=0.1)
norm = ImageNormalize(img_data, interval=interval, stretch=stretch)

fig, ax = plt.subplots(1, 1, figsize=(8, 8), facecolor="#0d1117")
ax.set_facecolor("#0d1117")
ax.imshow(img_data, norm=norm, cmap="gray", origin="lower")
ax.set_title(
    f"{{dataset_type}} | {{night}} | {{band}}", color="#e6edf3", fontsize=10)
ax.tick_params(colors="#8b949e", labelsize=7)
for spine in ax.spines.values():
    spine.set_color("#30363d")
fig.tight_layout(pad=1.0)
fig.savefig(output, dpi=100, bbox_inches="tight", facecolor="#0d1117")
plt.close(fig)
print("OK")
"""
    )


def _build_list_script(repo_path: str) -> str:
    """In-stack snippet printing a JSON list of available image datasets."""
    return (
        _preamble(repo_path)
        + _query_refs_helper()
        + f"""
dataset_types = {IMAGE_DATASET_TYPES!r}
results = []
seen = set()
for dt in dataset_types:
    for ref in _query_refs(dt):
        did = ref.dataId
        night = str(did.get("day_obs", ""))[:8]
        band = did.get("band", did.get("physical_filter", "?"))
        key = f"{{night}}_{{band}}_{{dt}}"
        if key not in seen:
            seen.add(key)
            results.append({{"night": night, "band": band, "dataset_type": dt}})
print(json.dumps(results))
"""
    )
