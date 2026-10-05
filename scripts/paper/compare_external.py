#!/usr/bin/env python
"""Quantify STIPS supernova photometry against independent references.

Compares nightly-median STIPS forced photometry (difference images, PSF flux)
with:

  SN 2023ixf  an independent reduction of the same Nickel frames
              (analysis/2023ixf_nickel_phot.cat; AB mags in B V r i; rows
              flagged "Bad" dropped). Matched by night (|dMJD| < 0.5 d).
  SN 2020wnt  Tinyanont et al. 2023 (ApJ 951, 34) per-band tables
              (analysis/2020wnt_photometry_20220916/2020wnt_<band>.dat, days
              from r peak). Interpolated to each STIPS epoch where the
              published curve has points within 5 d on both sides.

Writes <out>/external_<sn>.csv (matched pairs) and <out>/external_summary.json
(per SN and band: N, median offset STIPS - reference, robust scatter).

Usage:
  compare_external.py --fphot-2023ixf products/2023ixf/forced_phot_all.csv \
                      --fphot-2020wnt products/2020wnt/forced_phot_all.csv \
                      --out products/external
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF_2023IXF = ROOT / "analysis" / "2023ixf_nickel_phot.cat"
REF_2020WNT = ROOT / "analysis" / "2020wnt_photometry_20220916"
EXPLOSION = {"2023ixf": 60082.75, "2020wnt": 59180.0}
# Days from STIPS's reference epoch to Tinyanont's day 0 (r-band peak); the
# value the figure script uses (scripts/analysis/plot_sn_vs_ztf.py).
PEAK_OFFSET_2020WNT = 33.0
AB_NJY_ZP = 31.4
MIN_SNR = 5.0
# STIPS band -> reference band. Nickel has two filter families: Sloan-like
# rp/ip (PS1 AB, the like-for-like comparison) and Cousins r/i (Landolt
# colour terms, Vega-like, so an offset from AB references is expected).
REF_BAND = {"rp": "r", "ip": "i", "r": "r", "i": "i"}


def stips_nightly(path: Path) -> dict[tuple[str, str], tuple[float, float, float, int]]:
    """(day_obs, band) -> (mjd, median mag, error of the median, n)."""
    per = defaultdict(list)
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["dataset_type"] != "forced_phot_diffim_radec":
                continue
            flux, err = float(row["diffFlux"]), float(row["diffFluxErr"])
            if not (math.isfinite(flux) and flux > 0 and flux / err >= MIN_SNR):
                continue
            mag = AB_NJY_ZP - 2.5 * math.log10(flux)
            per[(row["day_obs"], row["band"])].append((float(row["mjd_mid"]), mag))
    out = {}
    for key, pts in per.items():
        mags = [m for _, m in pts]
        med = statistics.median(mags)
        spread = statistics.pstdev(mags) if len(mags) > 1 else 0.02
        out[key] = (
            statistics.mean(t for t, _ in pts),
            med,
            1.2533 * spread / math.sqrt(len(mags)),
            len(mags),
        )
    return out


def robust_std(values: list[float]) -> float:
    med = statistics.median(values)
    return 1.4826 * statistics.median(abs(v - med) for v in values)


def ref_2023ixf() -> dict[str, list[tuple[float, float, float]]]:
    ref = defaultdict(list)
    for line in REF_2023IXF.read_text().splitlines():
        parts = line.split()
        if len(parts) < 11 or parts[0] != "OBS:" or parts[-1].lower() == "bad":
            continue
        ref[parts[2].lower()].append(
            (float(parts[1]), float(parts[5]), float(parts[6]))
        )
    return ref


def compare_2023ixf(fphot: Path) -> list[dict]:
    ref = ref_2023ixf()
    rows = []
    for (day_obs, band), (mjd, mag, err, n) in sorted(stips_nightly(fphot).items()):
        if band not in REF_BAND:
            continue
        same_night = [r for r in ref.get(REF_BAND[band], []) if abs(r[0] - mjd) < 0.5]
        if not same_night:
            continue
        ref_mag = statistics.median(r[1] for r in same_night)
        ref_err = statistics.median(r[2] for r in same_night) / math.sqrt(
            len(same_night)
        )
        rows.append(dict(sn="2023ixf", band=band, day_obs=day_obs, mjd=round(mjd, 4),
                         phase=round(mjd - EXPLOSION["2023ixf"], 2), n_stips=n,
                         stips_mag=round(mag, 4), stips_err=round(err, 4),
                         ref_mag=round(ref_mag, 4), ref_err=round(ref_err, 4),
                         n_ref=len(same_night), delta=round(mag - ref_mag, 4)))  # fmt: skip
    return rows


def compare_2020wnt(fphot: Path) -> list[dict]:
    rows = []
    for (day_obs, band), (mjd, mag, err, n) in sorted(stips_nightly(fphot).items()):
        if band not in REF_BAND:
            continue
        table = REF_2020WNT / f"2020wnt_{REF_BAND[band]}.dat"
        if not table.exists():
            continue
        pts = sorted(
            (float(p[0]) + PEAK_OFFSET_2020WNT, float(p[1]), float(p[2]))
            for p in (ln.split() for ln in table.read_text().splitlines())
            if len(p) >= 3 and not p[0].startswith("#")
        )
        phase = mjd - EXPLOSION["2020wnt"]
        before = [p for p in pts if phase - 5 <= p[0] <= phase]
        after = [p for p in pts if phase <= p[0] <= phase + 5]
        if not before or not after:
            continue
        (t0, m0, e0), (t1, m1, e1) = before[-1], after[0]
        w = 0.0 if t1 == t0 else (phase - t0) / (t1 - t0)
        ref_mag, ref_err = m0 + w * (m1 - m0), max(e0, e1)
        rows.append(dict(sn="2020wnt", band=band, day_obs=day_obs, mjd=round(mjd, 4),
                         phase=round(phase, 2), n_stips=n, stips_mag=round(mag, 4),
                         stips_err=round(err, 4), ref_mag=round(ref_mag, 4),
                         ref_err=round(ref_err, 4), n_ref=2,
                         delta=round(mag - ref_mag, 4)))  # fmt: skip
    return rows


def summarize(rows: list[dict]) -> dict:
    out = {}
    for band in sorted({r["band"] for r in rows}):
        d = [r["delta"] for r in rows if r["band"] == band]
        out[band] = {
            "n_nights": len(d),
            "median_offset_mag": round(statistics.median(d), 3),
            "robust_scatter_mag": round(robust_std(d), 3) if len(d) > 2 else None,
            "phase_range_days": [
                min(r["phase"] for r in rows if r["band"] == band),
                max(r["phase"] for r in rows if r["band"] == band),
            ],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fphot-2023ixf", type=Path)
    ap.add_argument("--fphot-2020wnt", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {
        "method": "nightly median STIPS diffim PSF mag (S/N>=5) minus reference",
        "bands": "rp/ip = Sloan-like (AB, like-for-like); r/i = Cousins (Vega-like)",
        "references": {
            "2023ixf": "independent reduction of the same Nickel frames",
            "2020wnt": "Tinyanont et al. 2023, ApJ 951, 34 "
            f"(day 0 = STIPS epoch + {PEAK_OFFSET_2020WNT} d)",
        },
    }
    for sn, path, fn in (
        ("2023ixf", args.fphot_2023ixf, compare_2023ixf),
        ("2020wnt", args.fphot_2020wnt, compare_2020wnt),
    ):
        if not path:
            continue
        rows = fn(path)
        if rows:
            with open(args.out / f"external_{sn}.csv", "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        summary[sn] = summarize(rows)
    (args.out / "external_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
