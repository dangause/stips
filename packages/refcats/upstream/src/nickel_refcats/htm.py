from __future__ import annotations

from typing import List, Tuple


def cones_to_htm(cones: List[Tuple[float, float, float]], depth: int = 7) -> list[int]:
    """
    cones: [(ra_deg, dec_deg, radius_deg)]
    returns sorted unique HTM ids covering all cones at `depth`.
    """
    import lsst.geom as geom
    from lsst.meas.algorithms.htmIndexer import HtmIndexer

    htm = HtmIndexer(depth=depth)
    ids = set()
    for ra, dec, rad_deg in cones:
        center = geom.SpherePoint(ra * geom.degrees, dec * geom.degrees)
        shards, _ = htm.getShardIds(center, rad_deg * geom.degrees)
        ids.update(shards)
    return sorted(ids)
