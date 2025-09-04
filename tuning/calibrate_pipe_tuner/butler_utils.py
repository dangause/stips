from __future__ import annotations
from pathlib import Path
from typing import Any, List, Optional

def discover_postisr(repo: Path) -> str:
    """Return latest Nickel postISR run collection, or '' if none."""
    from lsst.daf.butler import Butler
    b = Butler(str(repo))
    cands = [str(rec) for rec in b.registry.queryCollections()
             if str(rec).startswith("Nickel/run/processCcd/")]
    return sorted(cands)[-1] if cands else ""

def discover_all_science_visits(repo: Path) -> List[int]:
    """Return all visit IDs for Nickel science exposures in this repo.

    Tries a direct visit-dimension query; if that fails, falls back to
    scanning data IDs over RAW datasets.
    """
    from lsst.daf.butler import Butler
    b = Butler(str(repo))

    try:
        recs = b.registry.queryDimensionRecords(
            "visit",
            where="instrument='Nickel' AND exposure.observation_type='science'",
        )
        return sorted(int(r.id) for r in recs)
    except Exception:
        pass

    try:
        q = b.registry.queryDataIds(
            dimensions={"instrument", "visit", "detector"},
            datasets="raw",
            where="instrument='Nickel' AND exposure.observation_type='science'",
        )
        visits = {int(d["visit"]) for d in q}
        return sorted(visits)
    except Exception as e:
        raise RuntimeError(
            f"Could not discover visits automatically: {e}\n"
            "Try specifying --visits explicitly."
        )

def read_visit_summaries(coll: str, repo: Path, visits: List[int]) -> List[Any]:
    """Fetch visitSummary tables (as Astropy rows) for given visits from a collection."""
    from lsst.daf.butler import Butler
    butler = Butler(str(repo), collections=coll, instrument="Nickel")
    rows: List[Any] = []
    for v in visits:
        try:
            vs = butler.get("visitSummary", {"instrument": "Nickel", "visit": int(v)})
            tbl = vs.asAstropy()
            if len(tbl) > 0:
                rows.append(tbl[0])
        except Exception:
            pass
    return rows

def median_from_rows(rows: List[Any], field: str) -> Optional[float]:
    """Median of a numeric column from a list of Astropy row objects (or None)."""
    vals: List[float] = []
    for r in rows:
        try:
            vals.append(float(r[field]))
        except Exception:
            pass
    if not vals:
        return None
    vals.sort()
    n = len(vals)
    return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])
