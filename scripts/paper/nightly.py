#!/usr/bin/env python
"""Nightly robust medians of per-visit supernova photometry.

The paper presents SN lightcurves one point per (night, band), because ~8% of
2023ixf's per-visit points are outliers (passing cloud, bad-WCS frames). The
rule, per (night, band):

  1. keep points with S/N >= 5;
  2. take the median magnitude;
  3. reject points more than max(3 * MAD, 0.15 mag) from it, where MAD is the
     normal-scaled median absolute deviation (1.4826 * raw MAD);
  4. recompute the median from the survivors;
  5. error = error of the median, 1.2533 * std / sqrt(n) (population std of
     the survivors), or the point's own error when n = 1.

The night is the UT day_obs, floor(MJD): it equals the Butler ``day_obs`` for
every Nickel row (Lick observes UT ~03-13 h, so no night straddles 0 h UT).
Bands are never merged: rp/ip (AB) and r/i (Vega) stay separate series.

Shared by ``compare_external.py`` and ``scripts/analysis/plot_sn_vs_ztf.py``.

Usage:
  nightly.py products/2023ixf/lightcurve.csv   # -> lightcurve_nightly.csv beside it
"""

from __future__ import annotations

import argparse
import csv
import datetime
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

MIN_SNR = 5.0
CLIP_NSIGMA = 3.0
CLIP_FLOOR_MAG = 0.15
MAD_TO_SIGMA = 1.4826
MEDIAN_ERR_FACTOR = 1.2533  # sqrt(pi/2): error of the median vs the mean
MJD_EPOCH = datetime.date(1858, 11, 17)

FIELDS = [
    "night", "band", "mag_system", "mjd", "days_since_explosion", "mag",
    "mag_err", "n_used", "n_rejected",
]  # fmt: skip


def ut_night(mjd: float) -> str:
    """UT day_obs (YYYYMMDD) of an MJD."""
    return (MJD_EPOCH + datetime.timedelta(days=math.floor(mjd))).strftime("%Y%m%d")


def _float(value) -> float:
    """float(value), with blanks (CSV non-detections) as NaN."""
    return float(value) if value not in (None, "") else math.nan


def robust_median(
    mags: list[float], errs: list[float]
) -> tuple[float, float, list[bool]]:
    """(median, error of the median, keep mask) for one night and band."""
    med = statistics.median(mags)
    mad = MAD_TO_SIGMA * statistics.median(abs(m - med) for m in mags)
    limit = max(CLIP_NSIGMA * mad, CLIP_FLOOR_MAG)
    keep = [abs(m - med) <= limit for m in mags]
    kept = [m for m, k in zip(mags, keep) if k]
    med = statistics.median(kept)
    if len(kept) == 1:
        err = next(e for e, k in zip(errs, keep) if k)
    else:
        err = MEDIAN_ERR_FACTOR * statistics.pstdev(kept) / math.sqrt(len(kept))
    return med, err, keep


def nightly(rows: Iterable[dict], min_snr: float = MIN_SNR) -> list[dict]:
    """Collapse per-visit rows to one robust median per (night, band).

    Each row needs float-able ``mjd``, ``band``, ``mag``, ``mag_err``, ``snr``;
    ``mag_system`` and ``days_since_explosion`` are carried through when
    present. Rows below ``min_snr`` or with a blank or non-finite mag are
    dropped.
    Output is sorted by band, then night.
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        mag, err, snr = (_float(row.get(k)) for k in ("mag", "mag_err", "snr"))
        if not (math.isfinite(mag) and math.isfinite(err) and snr >= min_snr):
            continue
        groups[(row["band"], ut_night(float(row["mjd"])))].append(row)
    out = []
    for (band, night), pts in sorted(groups.items()):
        mags = [float(p["mag"]) for p in pts]
        med, err, keep = robust_median(mags, [float(p["mag_err"]) for p in pts])
        kept = [p for p, k in zip(pts, keep) if k]
        days = [
            float(p["days_since_explosion"])
            for p in kept
            if p.get("days_since_explosion")
        ]
        out.append({
            "night": night,
            "band": band,
            "mag_system": pts[0].get("mag_system", ""),
            "mjd": statistics.mean(float(p["mjd"]) for p in kept),
            "days_since_explosion": statistics.mean(days) if days else math.nan,
            "mag": med,
            "mag_err": err,
            "n_used": len(kept),
            "n_rejected": len(pts) - len(kept),
        })  # fmt: skip
    return out


def format_row(row: dict) -> dict[str, str]:
    """A nightly row as CSV strings (what lightcurve_nightly.csv holds)."""
    return {
        **{k: str(row[k]) for k in FIELDS},
        "mjd": f"{row['mjd']:.5f}",
        "days_since_explosion": f"{row['days_since_explosion']:.3f}",
        "mag": f"{row['mag']:.4f}",
        "mag_err": f"{row['mag_err']:.4f}",
    }


def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(format_row(r) for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lightcurve", type=Path, nargs="+", help="per-visit lightcurve.csv")
    args = ap.parse_args()
    for path in args.lightcurve:
        with open(path, newline="") as fh:
            rows = nightly(csv.DictReader(fh))
        out = path.with_name("lightcurve_nightly.csv")
        write_csv(rows, out)
        print(f"wrote {out} ({len(rows)} night-band points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
