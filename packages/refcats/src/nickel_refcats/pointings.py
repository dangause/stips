from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import numpy as np


def uniq_pairs(
    ras: np.ndarray, decs: np.ndarray, ndp: int = 6
) -> tuple[np.ndarray, np.ndarray]:
    arr = np.column_stack([ras, decs])
    uniq = np.unique(np.round(arr, ndp), axis=0)
    return uniq[:, 0], uniq[:, 1]


def _unitvec_to_xyz(u) -> tuple[float, float, float]:
    if hasattr(u, "getX"):  # lsst.sphgeom
        return float(u.getX()), float(u.getY()), float(u.getZ())
    x = getattr(u, "x", None)
    x = x() if callable(x) else x
    y = getattr(u, "y", None)
    y = y() if callable(y) else y
    z = getattr(u, "z", None)
    z = z() if callable(z) else z
    return float(x), float(y), float(z)


def _region_centroid_radec(region) -> tuple[float, float]:
    verts = list(
        getattr(region, "getVertices", getattr(region, "getVerticesIter", lambda: []))()
    )
    if not verts:
        raise RuntimeError("region has no vertices")
    import numpy as np

    xyz = np.array([_unitvec_to_xyz(v) for v in verts], float)
    m = xyz.mean(axis=0)
    m /= np.linalg.norm(m)
    x, y, z = m
    ra = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    dec = math.degrees(math.asin(z))
    return ra, dec


def normalize_where(registry_where: str | None) -> str | None:
    if not registry_where:
        return None
    fields = (
        "observation_reason",
        "physical_filter",
        "day_obs",
        "target_name",
        "science_program",
    )
    out = registry_where
    for f in fields:
        out = re.sub(rf"(?<!\.)\b{f}\b", f"visit.{f}", out)
    return out


def pointings_from_butler(
    repo: str,
    instrument: str = "Nickel",
    include_calibs: bool = False,
    registry_where: str | None = None,
) -> Iterable[tuple[float, float]]:
    from lsst.daf.butler import Butler

    b = Butler(repo)
    where = f"instrument='{instrument}'"
    if registry_where:
        where += f" AND ({registry_where})"
    for v in b.registry.queryDimensionRecords("visit", where=where):
        if (
            not include_calibs
            and getattr(v, "observation_reason", None) == "calibration"
        ):
            tn = (getattr(v, "target_name", "") or "").lower()
            if any(k in tn for k in ("flat", "bias", "dark")):
                continue
        region = getattr(v, "region", None)
        if region is None:
            continue
        try:
            yield _region_centroid_radec(region)
        except Exception:
            continue


def _fits_paths(root: str | Path, recursive: bool) -> Iterable[Path]:
    root = Path(root)
    exts = (".fits", ".fit", ".fz", ".fits.fz", ".fit.fz", ".fts", ".fts.fz")
    if recursive:
        it = root.rglob("*")
    else:
        it = root.glob("*")  # <-- fixed: non-recursive
    for p in sorted(it):
        low = str(p).lower()
        if p.is_file() and (
            p.suffix.lower() in exts or any(low.endswith(e) for e in exts)
        ):
            yield p


def pointings_from_fits_dir(
    fits_dir: str | Path,
    recursive: bool,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
) -> Iterable[tuple[float, float]]:
    from astropy.io import fits
    from astropy.wcs import WCS

    rincl = re.compile(include_pattern) if include_pattern else None
    rexcl = re.compile(exclude_pattern) if exclude_pattern else None

    used = 0
    for p in _fits_paths(fits_dir, recursive):
        s = str(p)
        if rincl and not rincl.search(s):
            continue
        if rexcl and rexcl.search(s):
            continue
        try:
            with fits.open(p, memmap=False) as hdul:
                # pick the first HDU with data, else fall back to primary
                hdr = next(
                    (h.header for h in hdul if getattr(h, "data", None) is not None),
                    hdul[0].header,
                )
                try:
                    w = WCS(hdr)
                    nx = int(hdr.get("NAXIS1", 0))
                    ny = int(hdr.get("NAXIS2", 0))
                    if nx > 0 and ny > 0 and w.has_celestial:
                        # center pixel (0-based indexing)
                        sky = w.pixel_to_world((nx - 1) / 2.0, (ny - 1) / 2.0)
                        used += 1
                        yield float(sky.ra.deg), float(sky.dec.deg)
                        continue
                except Exception:
                    pass
                # fallback: CRVAL if present
                if "CRVAL1" in hdr and "CRVAL2" in hdr:
                    used += 1
                    yield float(hdr["CRVAL1"]), float(hdr["CRVAL2"])
                    continue
        except Exception:
            continue
    # Optional: print a small summary (only when used directly)
    if used == 0:
        print(f"[fits-scan] No usable FITS found in {fits_dir} (recursive={recursive})")


def pointings_from_pipeline_configs(
    config_paths: Iterable[str | Path],
) -> Iterable[tuple[float, float, str]]:
    """Yield (ra, dec, config_path) from pipeline YAML configs with top-level ra/dec keys."""
    import yaml

    for p in config_paths:
        p = Path(p)
        if not p.exists() or p.suffix not in (".yaml", ".yml"):
            continue
        try:
            cfg = yaml.safe_load(p.read_text())
            if not isinstance(cfg, dict):
                continue
            ra = cfg.get("ra")
            dec = cfg.get("dec")
            if ra is not None and dec is not None:
                yield float(ra), float(dec), str(p)
        except Exception:
            continue
