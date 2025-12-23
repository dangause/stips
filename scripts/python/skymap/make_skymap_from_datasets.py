#!/usr/bin/env python

"""
Build a DiscreteSkyMap from the WCS+BBox of a set of exposures (e.g. initial_pvi)
and persist it as dataset type 'skyMap', plus insert the skymap/tract dimension rows.

Example:
  python scripts/make_skymap_from_datasets.py \
    --repo /path/to/repo \
    --collections "Nickel/run/processCcd" \
    --dataset-type initial_pvi \
    --skymap-id nickel_discrete \
    --run "Nickel/skymaps/$(date -u +%Y%m%dT%H%M%SZ)" \
    --border-deg 0.05
"""

from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

import lsst.geom as geom
import lsst.sphgeom as sphgeom
from lsst.daf.butler import Butler, DatasetType
from lsst.geom import Box2D
from lsst.skymap import DiscreteSkyMap


def ensure_skyMap_dataset_type(butler: Butler) -> None:
    """Register the 'skyMap' DatasetType if missing."""
    try:
        butler.registry.getDatasetType("skyMap")
        print("[info] 'skyMap' DatasetType already registered")
        return
    except Exception:
        pass

    dims = butler.registry.dimensions["skymap"]
    dt = DatasetType("skyMap", dims, "SkyMap")
    butler.registry.registerDatasetType(dt)
    print("[info] Registered DatasetType 'skyMap' (dimensions=skymap, SC=SkyMap)")


def ensure_run_collection(butler: Butler, run: str) -> None:
    """Create a RUN collection if needed."""
    try:
        butler.registry.registerRun(run)
        print(f"[info] Created RUN collection: {run}")
    except Exception:
        # Already exists or another benign condition
        pass


def collect_wcs_bbox(
    butler: Butler,
    dataset_type: str,
    collections: List[str],
) -> List[Tuple[geom.SkyWcs, geom.Box2I]]:
    """Gather (Wcs, BBox) pairs for all datasets of the given type in collections."""
    dsrefs = list(butler.registry.queryDatasets(dataset_type, collections=collections))
    if not dsrefs:
        raise RuntimeError(
            f"No datasets of type '{dataset_type}' found in {collections}"
        )

    print(f"[info] Found {len(dsrefs)} {dataset_type} in {collections}")
    out: List[Tuple[geom.SkyWcs, geom.Box2I]] = []
    for ref in dsrefs:
        exp = butler.get(ref)
        out.append((exp.getWcs(), exp.getBBox()))
    return out


def convex_hull_from_wcs_bboxes(
    pairs: Iterable[Tuple[geom.SkyWcs, geom.Box2I]],
) -> sphgeom.ConvexPolygon:
    """Mirror of MakeDiscreteSkyMapTask: convex hull of all exposure corner sky positions."""
    points = []
    for wcs, boxI in pairs:
        boxD = Box2D(boxI)
        for corner in boxD.getCorners():
            sp = wcs.pixelToSky(corner)
            points.append(sp.getVector())  # UnitVector3d
    if not points:
        raise RuntimeError("No data found from which to compute convex hull")
    polygon = sphgeom.ConvexPolygon.convexHull(points)
    if polygon is None:
        raise RuntimeError(
            "Failed to compute convex hull; corners may be hemispherical."
        )
    return polygon


def build_discrete_skymap_from_polygon(
    polygon: sphgeom.ConvexPolygon,
    border_deg: float = 0.0,
) -> DiscreteSkyMap:
    """Create a DiscreteSkyMap with one tract that fully encloses the convex hull (+ border)."""
    circle = polygon.getBoundingCircle()
    center_ll = sphgeom.LonLat(circle.getCenter())
    ra_deg = center_ll[0].asDegrees()
    dec_deg = center_ll[1].asDegrees()
    radius_deg = circle.getOpeningAngle().asDegrees() + float(border_deg)

    cfg = DiscreteSkyMap.ConfigClass()
    # Keep defaults like tractOverlap=0 as in MakeDiscreteSkyMapConfig.setDefaults
    cfg.raList = [ra_deg]
    cfg.decList = [dec_deg]
    cfg.radiusList = [radius_deg]

    skyMap = DiscreteSkyMap(cfg)

    # Log tract geometry
    for tractInfo in skyMap:
        w = tractInfo.getWcs()
        posBox = geom.Box2D(tractInfo.getBBox())
        pixelPosList = (
            posBox.getMin(),
            geom.Point2D(posBox.getMaxX(), posBox.getMinY()),
            posBox.getMax(),
            geom.Point2D(posBox.getMinX(), posBox.getMaxY()),
        )
        skyPosList = [w.pixelToSky(p).getPosition(geom.degrees) for p in pixelPosList]
        s = ", ".join(f"({ra:.3f}, {dec:.3f})" for (ra, dec) in skyPosList)
        nx, ny = tractInfo.getNumPatches()
        print(f"[info] tract {tractInfo.getId()} corners {s} and {nx} x {ny} patches")

    return skyMap


def upsert_dimensions_for_skymap(
    butler: Butler, skymap_id: str, skyMap: DiscreteSkyMap
) -> None:
    """Insert dimension rows for 'skymap' and 'tract' with required fields."""
    # skymap row (name only)
    try:
        butler.registry.insertDimensionData("skymap", [{"skymap": skymap_id}])
        print(f"[info] Inserted skymap dimension row: {skymap_id}")
    except Exception:
        # Already present
        pass

    inserted = skipped = 0
    for ti in skyMap:
        # REQUIRED field is 'region'; include it.
        row = {
            "skymap": skymap_id,
            "tract": int(ti.getId()),
            "region": ti.getOuterSkyPolygon(),
        }
        # Optional: include patch grid maxima (harmless if schema ignores)
        try:
            nx, ny = ti.getNumPatches()
            row["patch_nx_max"] = int(nx)
            row["patch_ny_max"] = int(ny)
        except Exception:
            pass

        try:
            butler.registry.insertDimensionData("tract", [row])
            inserted += 1
        except Exception:
            skipped += 1

    print(f"[ok] Dimension rows: tract inserted={inserted}, skipped={skipped}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create and persist a DiscreteSkyMap from exposure footprints."
    )
    p.add_argument("--repo", required=True, help="Butler repo path/URI")
    p.add_argument(
        "--collections",
        required=True,
        help="Comma-separated collection(s) to read from",
    )
    p.add_argument(
        "--dataset-type",
        default="initial_pvi",
        help="Dataset type to sample (default: initial_pvi)",
    )
    p.add_argument(
        "--skymap-id",
        required=True,
        help="Identifier for the skyMap dimension row (e.g. nickel_discrete)",
    )
    p.add_argument(
        "--run", required=True, help="RUN collection to write the skyMap dataset into"
    )
    p.add_argument(
        "--border-deg",
        type=float,
        default=0.0,
        help="Extra border (deg) added to convex-hull radius",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    colls = [c.strip() for c in args.collections.split(",") if c.strip()]
    print(f"[info] Using collections: {colls}")

    # Writable Butler (we control read via explicit collections on query/get)
    butler = Butler(args.repo, writeable=True)

    # Ensure dataset type + run exist
    ensure_skyMap_dataset_type(butler)
    ensure_run_collection(butler, args.run)

    # Build convex hull from the selected datasets
    pairs = collect_wcs_bbox(butler, args.dataset_type, colls)
    polygon = convex_hull_from_wcs_bboxes(pairs)

    # Produce a 1-tract DiscreteSkyMap that encloses all exposures (+ border)
    skyMap = build_discrete_skymap_from_polygon(polygon, border_deg=args.border_deg)

    # Persist the SkyMap object
    butler.put(skyMap, "skyMap", {"skymap": args.skymap_id}, run=args.run)
    print(f"[ok] Wrote skyMap skymap='{args.skymap_id}' to run '{args.run}'")

    # Upsert skymap + tract dimension rows (includes required 'region')
    upsert_dimensions_for_skymap(butler, args.skymap_id, skyMap)


if __name__ == "__main__":
    main()
