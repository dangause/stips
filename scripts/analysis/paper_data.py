"""Where the figure scripts find their inputs.

Set ``STIPS_PAPER_DATA`` to a paper rebuild's ``products/`` directory
(written by ``scripts/paper/rebuild.py``) to draw every figure from that
frozen rebuild. Unset, scripts fall back to the legacy ``analysis/`` folder.

The rebuild writes the same file names the scripts always used
(``calib_metrics/combined.csv``, ``landolt_validation_4nights.csv``,
``lightcurve_<target>.csv``), so only the root changes.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def data_root() -> Path:
    env = os.environ.get("STIPS_PAPER_DATA")
    return Path(env) if env else REPO_ROOT / "analysis"


def data(*parts: str) -> Path:
    """A file under the data root."""
    return data_root().joinpath(*parts)


def figure(*parts: str) -> Path:
    """Where a figure is written: ``<rebuild>/figures/`` beside a rebuild's
    ``products/`` when ``STIPS_PAPER_DATA`` is set, else the legacy
    ``analysis/`` folder. The parent directory is created."""
    env = os.environ.get("STIPS_PAPER_DATA")
    base = Path(env).parent / "figures" if env else REPO_ROOT / "analysis"
    path = base.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def repo(target: str) -> Path:
    """The rebuild's Butler repo for ``target`` (``<out>/repos/<target>_repo``)."""
    env = os.environ.get("STIPS_PAPER_DATA")
    if not env:
        raise SystemExit(
            f"{target}: set STIPS_PAPER_DATA to a rebuild's products/ dir; "
            "the legacy repos these scripts once used were deleted."
        )
    return Path(env).parent / "repos" / f"{target}_repo"


def find_file(repo_dir: Path, pattern: str) -> Path:
    """The newest file under ``repo_dir`` whose name matches ``pattern``."""
    hits = sorted(glob.glob(str(repo_dir / "**" / pattern), recursive=True))
    if not hits:
        raise SystemExit(f"no file matching {pattern} under {repo_dir}")
    return Path(hits[-1])


def dataset_file(repo_dir: Path, dataset_type: str, visit: int) -> Path:
    """The FITS file of ``dataset_type`` for ``visit`` in a repo.

    The instrument name follows the dataset type and is capitalised
    (``preliminary_visit_image_Nickel_...``), which excludes sibling datasets
    that share the prefix (``preliminary_visit_image_background_...``,
    ``difference_image_predetection_...``). Of several RUNs the newest
    fallback wins (``run_fb2`` > ``run_fb1`` > ``run``), matching the chain.
    """
    return find_file(repo_dir, f"{dataset_type}_[A-Z]*_{visit}_*.fits")
