#!/usr/bin/env python
# Build a Discrete SkyMap config (pex_config) from the convex hull of
# all initial_pvi images in one or more collections.
#
# Usage (example):
#   python scripts/build_discrete_skymap_config.py \
#     --repo /path/to/repo \
#     --collections Nickel/run/processCcd \
#     --dataset-type initial_pvi \
#     --skymap-id nickel_discrete \
#     --border-deg 0.05 \
#     --out configs/makeSkyMap_discrete_auto.py
#
# Then register:
#   butler register-skymap /path/to/repo -C configs/makeSkyMap_discrete_auto.py
#
# Notes:
# - We fetch only WCS + BBox components (fast) and avoid loading pixels.
# - Pixel scale is taken as the median across inputs, with optional override.

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median

import lsst.geom as geom
import lsst.sphgeom as sphgeom
from lsst.daf.butler import Butler


def _get_wcs_and_bbox(butler: Butler, dsref, dtype: str, collections):
    """Fetch WCS and BBox components for a dataset (fast), with a fallback to
    loading the full exposure if components are unavailable."""
    dataId = dsref.dataId

    # Try exposure components first (preferred).
    wcs = bbox = None
    try:
        wcs = butler.get(f"{dtype}.wcs", dataId, collections=collections)
    except Exception:
        pass
    try:
        bbox = butler.get(f"{dtype}.bbox", dataId, collections=collections)
    except Exception:
        pass

    if wcs is not None and bbox is not None:
        return wcs, bbox

    # Fallback: read the full exposure (slower, but robust).
    exp = butler.get(dtype, dataId, collections=collections)
    return exp.getWcs(), exp.getBBox()


def _hull_center_radius_deg(wcs_bbox_pairs: list[tuple], border_deg: float):
    """Compute spherical convex hull of all image corners, then return
    (center_ra_deg, center_dec_deg, radius_deg [+ border])."""
    points = []
    for wcs, boxI in wcs_bbox_pairs:
        boxD = geom.Box2D(boxI)
        for corner in boxD.getCorners():
            points.append(wcs.pixelToSky(corner).getVector())  # UnitVector3d

    if not points:
        raise RuntimeError("No corners gathered; are there any images?")

    poly = sphgeom.ConvexPolygon.convexHull(points)
    if poly is None:
        raise RuntimeError("Convex hull failed (input may span > hemisphere).")

    circ = poly.getBoundingCircle()
    ctr = sphgeom.LonLat(circ.getCenter())
    ra_deg = ctr[0].asDegrees()
    dec_deg = ctr[1].asDegrees()
    rad_deg = circ.getOpeningAngle().asDegrees() + float(border_deg)
    return ra_deg, dec_deg, rad_deg


def _median_pixscale_arcsec(
    wcs_bbox_pairs: list[tuple], fallback: float | None = None
) -> float:
    vals = []
    for wcs, _ in wcs_bbox_pairs:
        try:
            vals.append(wcs.getPixelScale().asArcseconds())
        except Exception:
            pass
    if vals:
        return float(median(vals))
    if fallback is None:
        raise RuntimeError("Could not determine pixel scale and no fallback provided.")
    return float(fallback)


def main():
    ap = argparse.ArgumentParser(
        description="Build a discrete SkyMap config from initial_pvi footprints."
    )
    ap.add_argument("--repo", required=True, help="Butler repo path")
    ap.add_argument(
        "--collections",
        required=True,
        nargs="+",
        help="One or more input collections to search (order matters)",
    )
    ap.add_argument(
        "--dataset-type",
        default="initial_pvi",
        help="Dataset type to use for footprints (default: initial_pvi)",
    )
    ap.add_argument(
        "--skymap-id",
        default="nickel_discrete",
        help="Skymap identifier (coadd name) to write into config",
    )
    ap.add_argument(
        "--border-deg",
        type=float,
        default=0.05,
        help="Extra border (deg) added to the bounding circle",
    )
    ap.add_argument(
        "--pixel-scale-arcsec",
        type=float,
        default=None,
        help="Override pixel scale (arcsec/pix). If omitted, median of inputs is used.",
    )
    ap.add_argument(
        "--out", required=True, help="Output config file path (pex_config python)"
    )
    args = ap.parse_args()

    butler = Butler(args.repo, writeable=False)

    # Find inputs
    dsrefs = list(
        butler.registry.queryDatasets(args.dataset_type, collections=args.collections)
    )
    if not dsrefs:
        raise SystemExit(f"No '{args.dataset_type}' found in {args.collections}")

    # Gather WCS+BBox; keep a few for scale calc too
    pairs = []
    for ds in dsrefs:
        try:
            wcs, bbox = _get_wcs_and_bbox(
                butler, ds, args.dataset_type, args.collections
            )
            pairs.append((wcs, bbox))
        except Exception as e:
            print(f"[warn] skipping {ds.id}: {e}")

    if not pairs:
        raise SystemExit("No usable WCS/BBox pairs; cannot build SkyMap.")

    # Convex hull -> center+radius
    ra_deg, dec_deg, radius_deg = _hull_center_radius_deg(pairs, args.border_deg)

    # Pixel scale (median or override)
    pixscale_as = (
        _median_pixscale_arcsec(pairs, fallback=None)
        if args.pixel_scale_arcsec is None
        else float(args.pixel_scale_arcsec)
    )

    # Write config (registry-style; works with `butler register-skymap`)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("# Auto-generated Discrete SkyMap config")
    lines.append(f'config.name = "{args.skymap_id}"')
    lines.append('config.skyMap.name = "discrete"')
    lines.append('d = config.skyMap["discrete"]')
    lines.append(f"d.raList     = [{ra_deg:.6f}]     # deg")
    lines.append(f"d.decList    = [{dec_deg:.6f}]    # deg")
    lines.append(
        f"d.radiusList = [{radius_deg:.6f}] # deg (includes border {args.border_deg} deg)"
    )
    lines.append(f"d.pixelScale   = {pixscale_as:.6f}  # arcsec/pixel")
    lines.append("d.tractOverlap = 0.0                 # deg")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[ok] wrote config: {out}")
    print(
        f"[info] name={args.skymap_id}  center=({ra_deg:.6f},{dec_deg:.6f}) deg  radius={radius_deg:.6f} deg"
    )
    print(f"[hint] register with:\n  butler register-skymap {args.repo} -C {out}")


if __name__ == "__main__":
    main()
