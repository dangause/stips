"""Wrap LSST convertReferenceCatalog (logic moved from scripts/convert_refcats.py).

The actual conversion shells out to the ``convertReferenceCatalog`` CLI, which
requires the LSST stack to be set up. Only this thin wrapper lives here so that
callers (and tests) can drive the fetch/convert/ingest flow without importing
``lsst.*`` at module load time.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def convert_catalog(
    name: str,
    source_csv: Path,
    config_path: Path,
    out_dir: Path,
    *,
    force: bool = False,
) -> Path:
    """Run convertReferenceCatalog for one catalog if needed.

    Parameters
    ----------
    name
        Short label used in messages (e.g. ``"GAIA"`` / ``"PS1"``).
    source_csv
        Pre-fetched catalog CSV with the columns the ``config_path`` expects.
    config_path
        ``convertReferenceCatalog`` config file (e.g. ``gaia_dr3_config.py``).
    out_dir
        Output directory for the tiled refcat + ``filename_to_htm.ecsv``.
    force
        Re-run even if a map already exists.

    Returns
    -------
    Path
        Path to ``filename_to_htm.ecsv`` produced by the conversion.

    Raises
    ------
    FileNotFoundError
        If the input CSV is missing, or the expected map is absent afterward.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmap = out_dir / "filename_to_htm.ecsv"

    if fmap.exists() and not force:
        return fmap
    if not Path(source_csv).exists():
        raise FileNotFoundError(f"[{name}] Missing input CSV: {source_csv}")

    subprocess.run(
        ["convertReferenceCatalog", str(out_dir), str(config_path), str(source_csv)],
        check=True,
    )
    if not fmap.exists():
        raise FileNotFoundError(
            f"[{name}] Expected map not found after conversion: {fmap}"
        )
    return fmap
