#!/usr/bin/env python3
"""
Determine fluxMag0T1 for Nickel filters from already-processed data.

Works with obs_nickel DRP.yaml that writes:
  - preliminary_visit_image (preferred) and/or
  - preliminary_visit_summary
and also handles classic:
  - visit_image or calexp
  - visitSummary

Method (default):
  Per (visit, band) load one exposure, get PhotoCalib, compute S (nJy per 1 instFlux):
      S = photoCalib.instFluxToNanojansky(1.0)
  Then: fluxMag0T1 = 3631e9 / S
  Aggregate per band (median, scatter).

Usage:
  python scripts/colorterms/determine_fluxMag0T1.py \
      --repo $REPO \
      --collection Nickel/runs/YYYYMMDD/processCcd/TIMESTAMP \
      --output-dir scripts/colorterms/calib_results \
      --bands B V R I
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from lsst.daf.butler import Butler

# ---------------- Utilities ----------------

EXPOSURE_DTYPES_PREFERRED = [
    "preliminary_visit_image",
    "visit_image",
    "calexp",
]

SUMMARY_DTYPES_FALLBACK = [
    "preliminary_visit_summary",
    "visitSummary",
]


def _band_key_from_ref(ref):
    # Prefer physical_filter; fall back to 'band'.
    phys = ref.dataId.get("physical_filter")
    band = ref.dataId.get("band")
    key = phys or band or "UNK"
    return str(key).upper()


def _query_any_dtype(butler, dtypes, collection, where):
    """Return (dtype, list_of_dataset_refs) for the first dtype that has data."""
    for dt in dtypes:
        refs = list(
            butler.registry.queryDatasets(dt, collections=collection, where=where)
        )
        if refs:
            return dt, refs
    return None, []


# ---------------- Core solver ----------------


def compute_from_exposures(butler, collection, bands=None, visits=None, outdir=None):
    """Compute fluxMag0T1 per band by reading PhotoCalib from *exposures*."""
    where = ["instrument='Nickel'"]
    if bands:
        ors = []
        for b in bands:
            # Nickel writes lower-case band and upper-case physical_filter
            ors.append(f"(band='{b.lower()}' OR physical_filter='{b}')")
        where.append("(" + " OR ".join(ors) + ")")
    if visits:
        where.append(f"visit IN ({','.join(str(v) for v in visits)})")
    where = " AND ".join(where)

    # Find which exposure dataset type exists in this collection.
    chosen_dt, refs = _query_any_dtype(
        butler, EXPOSURE_DTYPES_PREFERRED, collection, where
    )
    if not refs:
        return None, {}

    print(f"[info] Using exposure dtype: {chosen_dt}  ({len(refs)} dataset refs total)")

    # Group refs by (band, visit). If multiple detectors exist, we just use the first per visit.
    by_band_visit = {}
    for ref in refs:
        band = _band_key_from_ref(ref)
        visit = ref.dataId.get("visit")
        if visit is None:
            # Shouldn't happen for these dtypes, but be safe.
            continue
        key = (band, int(visit))
        if key not in by_band_visit:
            by_band_visit[key] = ref  # first ref for this (band, visit)

    # Prepare per-band accumulation.
    per_band_zp = defaultdict(list)
    per_band_vis = defaultdict(list)

    # Iterate over unique (band, visit) and compute ZP.
    for (band, visit), ref in sorted(by_band_visit.items()):
        if bands and band not in bands:
            continue
        try:
            exposure = butler.get(ref)
        except Exception as e:
            print(
                f"  [warn] visit={visit} band={band}: failed to load {chosen_dt}: {e}"
            )
            continue

        # Grab PhotoCalib and compute S
        pc = None
        try:
            pc = exposure.getPhotoCalib()
        except Exception:
            try:
                # In rare cases PhotoCalib may be attached differently; try attribute
                pc = getattr(exposure, "photoCalib", None)
            except Exception:
                pc = None

        if pc is None:
            print(
                f"  [warn] visit={visit} band={band}: missing PhotoCalib in {chosen_dt}"
            )
            continue

        # S = nJy per 1 instFlux
        try:
            S = pc.instFluxToNanojansky(1.0)
        except Exception:
            try:
                # very old stacks spelling
                S = pc.instFluxToNjansky(1.0)
            except Exception:
                print(
                    f"  [warn] visit={visit} band={band}: cannot call instFluxToNanojansky(1.0)"
                )
                continue

        if not np.isfinite(S) or S <= 0:
            print(f"  [warn] visit={visit} band={band}: invalid S={S}")
            continue

        # fluxMag0T1 and equivalent ZP
        fm0 = 3631e9 / S
        zp = 2.5 * np.log10(fm0)

        per_band_zp[band].append(zp)
        per_band_vis[band].append(int(visit))

    # Summarize
    results = {}
    for band in bands or sorted(per_band_zp.keys()):
        zps = per_band_zp.get(band, [])
        if not zps:
            print(f"\n--- BAND {band}: no valid visits with PhotoCalib ---")
            results[band] = None
            continue

        zp_arr = np.array(zps, dtype=float)
        med = float(np.median(zp_arr))
        sig = float(np.std(zp_arr))
        fm0 = 10.0 ** (med / 2.5)

        results[band] = dict(
            fluxMag0T1=fm0,
            zero_point=med,
            zp_scatter=sig,
            n_visits=len(zps),
            visit_zps=zp_arr,
            visit_ids=per_band_vis[band],
        )

        print(f"\nBAND {band}:")
        print(f"  visits     : {len(zps)}")
        print(f"  ZP median  : {med:.3f} mag  (σ={sig:.3f})")
        print(f"  fluxMag0T1 : {fm0:.3e}")

    # Optional quick plots
    if outdir:
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        for band, res in results.items():
            if not res:
                continue
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(range(len(res["visit_ids"])), res["visit_zps"], "o-")
            ax.axhline(
                res["zero_point"],
                linestyle="--",
                label=f"Median {res['zero_point']:.3f}",
            )
            ax.set_xlabel("Visit index")
            ax.set_ylabel("Zero point (mag)")
            ax.set_title(f"{band}: ZP scatter={res['zp_scatter']:.3f}")
            ax.grid(True, alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(out / f"fluxMag0T1_{band}_photo.png", dpi=150)
            plt.close(fig)

    return chosen_dt, results


def compute_from_summaries(butler, collection, bands=None, visits=None, outdir=None):
    """Fallback: compute from visit summary tables (if exposures not found)."""
    where = ["instrument='Nickel'"]
    if bands:
        ors = []
        for b in bands:
            ors.append(f"(band='{b.lower()}' OR physical_filter='{b}')")
        where.append("(" + " OR ".join(ors) + ")")
    if visits:
        where.append(f"visit IN ({','.join(str(v) for v in visits)})")
    where = " AND ".join(where)

    chosen_dt, refs = _query_any_dtype(
        butler, SUMMARY_DTYPES_FALLBACK, collection, where
    )
    if not refs:
        return None, {}

    print(f"[info] Using summary dtype: {chosen_dt}  ({len(refs)} dataset refs total)")

    per_band_zp = defaultdict(list)
    per_band_vis = defaultdict(list)

    # These are per-visit tables (possibly per-detector rows). Grab first row.
    for ref in refs:
        band = _band_key_from_ref(ref)
        if bands and band not in bands:
            continue
        visit = ref.dataId.get("visit")
        if visit is None:
            continue

        try:
            vs = butler.get(ref)
        except Exception as e:
            print(
                f"  [warn] visit={visit} band={band}: failed to load {chosen_dt}: {e}"
            )
            continue

        row = None
        try:
            # visitSummary behaves like a table; take first row
            row = vs[0]
        except Exception:
            # Some storage classes attach attributes instead
            row = getattr(vs, "first", None)

        # Try to obtain a PhotoCalib
        pc = None
        try:
            pc = row.getPhotoCalib()
        except Exception:
            pc = getattr(row, "photoCalib", None)

        if pc is None:
            print(
                f"  [warn] visit={visit} band={band}: missing PhotoCalib in {chosen_dt}"
            )
            continue

        try:
            S = pc.instFluxToNanojansky(1.0)
        except Exception:
            try:
                S = pc.instFluxToNjansky(1.0)
            except Exception:
                print(
                    f"  [warn] visit={visit} band={band}: cannot call instFluxToNanojansky(1.0)"
                )
                continue

        if not np.isfinite(S) or S <= 0:
            continue

        fm0 = 3631e9 / S
        zp = 2.5 * np.log10(fm0)

        per_band_zp[band].append(zp)
        per_band_vis[band].append(int(visit))

    results = {}
    for band in bands or sorted(per_band_zp.keys()):
        zps = per_band_zp.get(band, [])
        if not zps:
            print(f"\n--- BAND {band}: no valid visits in {chosen_dt} ---")
            results[band] = None
            continue
        arr = np.array(zps, dtype=float)
        med = float(np.median(arr))
        sig = float(np.std(arr))
        fm0 = 10.0 ** (med / 2.5)
        results[band] = dict(
            fluxMag0T1=fm0,
            zero_point=med,
            zp_scatter=sig,
            n_visits=len(arr),
            visit_zps=arr,
            visit_ids=per_band_vis[band],
        )
        print(f"\nBAND {band}:")
        print(f"  visits     : {len(arr)}")
        print(f"  ZP median  : {med:.3f} mag  (σ={sig:.3f})")
        print(f"  fluxMag0T1 : {fm0:.3e}")

    return chosen_dt, results


# ---------------- CLI ----------------


def main():
    ap = argparse.ArgumentParser(description="Determine fluxMag0T1 for Nickel filters")
    ap.add_argument("--repo", required=True, help="Butler repository path")
    ap.add_argument(
        "--collection", required=True, help="Collection with processCcd outputs"
    )
    ap.add_argument(
        "--bands",
        nargs="+",
        default=["B", "V", "R", "I"],
        help="Bands to analyze (match physical_filter or band)",
    )
    ap.add_argument(
        "--visits", nargs="+", type=int, help="Optional list of visits to include"
    )
    ap.add_argument(
        "--output-dir",
        default="./fluxMag0T1_results",
        help="Directory for simple diagnostic plots",
    )
    args = ap.parse_args()

    args.bands = [b.upper() for b in args.bands]

    print("=" * 80)
    print("NICKEL fluxMag0T1 determination")
    print("=" * 80)
    print(f"Repo       : {args.repo}")
    print(f"Collection : {args.collection}")
    print(f"Bands      : {' '.join(args.bands)}")
    print()

    try:
        butler = Butler(args.repo, collections=args.collection)
    except Exception as e:
        print(f"ERROR: Butler open failed: {e}")
        sys.exit(1)

    # Prefer exposures; if none, fall back to visit summaries.
    chosen_dt, results = compute_from_exposures(
        butler,
        args.collection,
        bands=args.bands,
        visits=args.visits,
        outdir=args.output_dir,
    )
    if not results:
        print("[info] No exposure dataset type found; trying visit summaries...")
        chosen_dt, results = compute_from_summaries(
            butler,
            args.collection,
            bands=args.bands,
            visits=args.visits,
            outdir=args.output_dir,
        )

    if not results:
        print(
            "\nERROR: Could not find exposure or summary datasets in this collection "
            "for your instrument/band constraints."
        )
        # Helpful hint:
        print("\nTip: Check what’s present with, e.g.:")
        print(
            '  butler query-datasets "$REPO" preliminary_visit_image '
            '--collections "<your-collection>" --where "instrument=\'Nickel\'" | head'
        )
        sys.exit(2)

    print("\nPaste this into `pipelines/DRP.yaml`:")
    print("isr:")
    print("  config:")
    print("    fluxMag0T1:")
    for band in args.bands:
        res = results.get(band)
        if res:
            print(
                f"      {band}: {res['fluxMag0T1']:.3e}  "
                f"# ZP={res['zero_point']:.3f}±{res['zp_scatter']:.3f}  (nvis={res['n_visits']})"
            )
        else:
            print(f"      {band}: 2.00e+08  # no data")

    print("\nDONE.")


if __name__ == "__main__":
    main()
