#!/usr/bin/env python
"""
Build rectangular defect masks from cpFlat outputs, optionally merge with
manual rectangles, ingest as a Butler `defects` calib, and (optionally)
certify validity and save QA plots.

Changes:
- NEW: --invert-manual-y flips *manual* rectangles in Y to match a
       post-geometry-inversion detector frame.
- NEW defaults: all outputs (CSV + QA) go to ./scripts/defects/defects_<TS>/
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # safe in headless
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from lsst.daf.butler import Butler, DatasetType
from lsst.geom import Box2I, Extent2I, Point2I
from scipy.ndimage import binary_opening, find_objects, gaussian_filter, label

try:
    from lsst.ip.isr import Defects  # newer stacks
except ImportError:
    from lsst.afw.image import Defects  # older stacks


# ------------------------------ helpers --------------------------------


def ts_utc() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _query_flat_refs(b: Butler, instrument: str) -> list:
    """Return all flat refs available in *the Butler's active collections*."""
    return list(
        b.registry.queryDatasets(
            datasetType="flat",
            where=f"instrument='{instrument}'",
            findFirst=False,
        )
    )


def median_flat(b: Butler, instrument: str) -> Tuple[np.ndarray, list]:
    refs = _query_flat_refs(b, instrument)
    if not refs:
        raise RuntimeError(
            "No `flat` datasets found in the given collection(s). "
            "Make sure --collection includes your cpFlat run."
        )
    arrs = [b.get(r).image.array.astype(np.float32) for r in refs]
    return np.median(np.stack(arrs, axis=0), axis=0), refs


def detect_rectangles_from_flat(
    img: np.ndarray,
    sigma_pix: int = 7,
    ratio_hi: float = 1.10,
    ratio_lo: float = 0.90,
    min_area_px: int = 8,
    open_kernel: int = 2,
) -> List[Tuple[int, int, int, int]]:
    """
    Return rectangles (x0, y0, w, h) indicating likely sensor defects.
    Works by smoothing + ratio thresholding + connected components.
    """
    img = img.astype(np.float32)
    smooth = gaussian_filter(img, sigma=sigma_pix)
    smooth = np.maximum(smooth, 1e-6)
    ratio = img / smooth

    mask = (ratio > ratio_hi) | (ratio < ratio_lo)
    if open_kernel > 0:
        mask = binary_opening(
            mask, structure=np.ones((open_kernel, open_kernel), dtype=bool)
        )

    labels, _ = label(mask)
    rects: List[Tuple[int, int, int, int]] = []
    for sl in find_objects(labels):
        if sl is None:
            continue
        ys, xs = sl
        h = int(ys.stop - ys.start)
        w = int(xs.stop - xs.start)
        if w * h < min_area_px:
            continue
        rects.append((int(xs.start), int(ys.start), w, h))
    return rects


def rectangles_to_boxes(rects: Iterable[Tuple[int, int, int, int]]) -> List[Box2I]:
    boxes: List[Box2I] = []
    for x0, y0, w, h in rects:
        boxes.append(Box2I(Point2I(int(x0), int(y0)), Extent2I(int(w), int(h))))
    return boxes


def masked_fraction(
    shape: Tuple[int, int], rects: Iterable[Tuple[int, int, int, int]]
) -> float:
    mask = np.zeros(shape, dtype=bool)
    for x0, y0, w, h in rects:
        mask[y0 : y0 + h, x0 : x0 + w] = True
    return float(mask.mean())


def ensure_defects_dataset_type(b: Butler):
    """Ensure 'defects' DatasetType exists and is marked calibration."""
    dims = b.registry.dimensions.conform({"instrument", "detector"})
    try:
        dt = b.registry.getDatasetType("defects")
        if not getattr(dt, "isCalibration", False):
            raise RuntimeError(
                "Existing dataset type 'defects' is not marked as calibration. "
                "Create a fresh repo or choose a different dataset type name."
            )
    except Exception:
        b.registry.registerDatasetType(
            DatasetType("defects", dims, "Defects", isCalibration=True)
        )


def save_overlay_png(
    img: np.ndarray, rects: List[Tuple[int, int, int, int]], title: str, out_png: str
):
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(img, origin="lower")
    for x0, y0, w, h in rects:
        ax.add_patch(patches.Rectangle((x0, y0), w, h, fill=False, linewidth=0.8))
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def save_mask_png(
    img: np.ndarray, rects: List[Tuple[int, int, int, int]], out_png: str
):
    mask = np.zeros_like(img, dtype=bool)
    for x0, y0, w, h in rects:
        mask[y0 : y0 + h, x0 : x0 + w] = True
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(mask, origin="lower")
    ax.set_title("Defect mask (True=masked)")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


# ----------------------- manual boxes utilities ------------------------


def _clip_box_to_bounds(
    x0: int, y0: int, w: int, h: int, nx: int, ny: int
) -> Optional[Tuple[int, int, int, int]]:
    """Clip (x0,y0,w,h) to [0..nx)×[0..ny); return None if fully out."""
    if w <= 0 or h <= 0:
        return None
    x1, y1 = x0 + w, y0 + h
    x0c = max(0, x0)
    y0c = max(0, y0)
    x1c = min(nx, x1)
    y1c = min(ny, y1)
    wc = x1c - x0c
    hc = y1c - y0c
    if wc <= 0 or hc <= 0:
        return None
    return int(x0c), int(y0c), int(wc), int(hc)


def _read_manual_csv(path: str) -> List[Tuple[int, int, int, int, str]]:
    """Read manual boxes CSV with columns x0,y0,width,height[,label]."""
    df = pd.read_csv(path)
    for col in ("x0", "y0", "width", "height"):
        if col not in df.columns:
            raise ValueError(f"Manual CSV missing required column: {col}")
    out: List[Tuple[int, int, int, int, str]] = []
    for _, row in df.iterrows():
        label = str(row.get("label", "manual"))
        out.append(
            (
                int(row["x0"]),
                int(row["y0"]),
                int(row["width"]),
                int(row["height"]),
                label,
            )
        )
    return out


def _dedupe_exact(
    rects: List[Tuple[int, int, int, int]],
) -> List[Tuple[int, int, int, int]]:
    """Remove exact duplicate (x0,y0,w,h) rectangles; preserve order."""
    seen = set()
    out: List[Tuple[int, int, int, int]] = []
    for x0, y0, w, h in rects:
        key = (x0, y0, w, h)
        if key in seen:
            continue
        seen.add(key)
        out.append((x0, y0, w, h))
    return out


# ------------------------------- CLI -----------------------------------


def main():
    ap = argparse.ArgumentParser(
        description="Create and (optionally) ingest Nickel defects from flats."
    )
    ap.add_argument("--repo", required=True, help="Butler repo path")
    ap.add_argument(
        "--collection",
        required=True,
        help="Collection(s) with flats (e.g. Nickel/run/cp_flat/...)",
    )
    ap.add_argument("--instrument", default="Nickel")
    ap.add_argument(
        "--detector",
        type=int,
        default=None,
        help="Detector id (default: infer from flats; Nickel=0)",
    )

    # Auto-detection controls
    ap.add_argument(
        "--sigma", type=int, default=7, help="Gaussian sigma (pixels) for smoothing"
    )
    ap.add_argument(
        "--ratio-hi",
        type=float,
        default=1.10,
        dest="ratio_hi",
        help="Upper ratio threshold",
    )
    ap.add_argument(
        "--ratio-lo",
        type=float,
        default=0.90,
        dest="ratio_lo",
        help="Lower ratio threshold",
    )
    ap.add_argument(
        "--min-area",
        type=int,
        default=8,
        dest="min_area",
        help="Minimum rectangle area (pixels)",
    )
    ap.add_argument(
        "--open",
        type=int,
        default=2,
        dest="open_kernel",
        help="Morphological opening kernel (square side)",
    )
    ap.add_argument(
        "--no-auto",
        action="store_true",
        help="Do not run automatic detection; use only manual rectangles.",
    )

    # Manual rectangles
    ap.add_argument(
        "--manual-box",
        action="append",
        nargs=4,
        type=int,
        metavar=("X0", "Y0", "W", "H"),
        help="Add a manual rectangle (LL x0,y0,width,height). Repeatable.",
    )
    ap.add_argument(
        "--manual-csv",
        type=str,
        default=None,
        help="CSV with columns x0,y0,width,height[,label] for manual rectangles.",
    )
    ap.add_argument(
        "--invert-manual-y",
        action="store_true",
        help="Mirror *manual* rectangles in Y (y -> ny - (y+height)). Use if you flipped the detector.",
    )

    # Outputs/ingest
    ap.add_argument(
        "--csv-out",
        default=None,
        help="Path to write rectangles CSV (default: ./scripts/defects/defects_<TS>/nickel_defects_rects_<TS>.csv)",
    )
    ap.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest defects to Butler after creating CSV",
    )
    ap.add_argument(
        "--register",
        action="store_true",
        help="Register dataset type 'defects' if missing",
    )
    ap.add_argument(
        "--defects-run",
        default=None,
        help="Run name for ingest (default: Nickel/calib/defects/<TS>)",
    )
    ap.add_argument(
        "--plot", action="store_true", help="Write PNG overlays/masks to QA dir"
    )
    ap.add_argument(
        "--qa-dir",
        default=None,
        help="Directory for QA PNGs (default: same ./scripts/defects/defects_<TS>/)",
    )
    # Optional certify
    ap.add_argument(
        "--certify",
        action="store_true",
        help="Certify validity in the calib chain (requires --begin/--end)",
    )
    ap.add_argument(
        "--begin", type=str, default=None, help="Begin date (YYYY-MM-DD) for certify"
    )
    ap.add_argument(
        "--end", type=str, default=None, help="End date (YYYY-MM-DD) for certify"
    )
    ap.add_argument(
        "--certify-to",
        type=str,
        default="Nickel/run/curated",
        help="Collection to certify into",
    )

    args = ap.parse_args()

    repo = os.path.expanduser(args.repo)

    # Butler for reading flats (collection-scoped)
    b_flat = Butler(repo, collections=args.collection)

    # Build median flat
    print(f"Building median flat from {args.collection} ...")
    med, refs = median_flat(b_flat, args.instrument)
    print(f"Using {len(refs)} flat(s)")
    ny, nx = med.shape  # NOTE: shape = (rows, cols) = (y, x)

    # ----------------- auto + manual rectangle assembly -----------------
    auto_rects: List[Tuple[int, int, int, int]] = []
    if not args.no_auto:
        auto_rects = detect_rectangles_from_flat(
            med,
            sigma_pix=args.sigma,
            ratio_hi=args.ratio_hi,
            ratio_lo=args.ratio_lo,
            min_area_px=args.min_area,
            open_kernel=args.open_kernel,
        )

    # Collect manual rectangles (optionally invert Y)
    manual_rects_labeled: List[Tuple[int, int, int, int, str]] = []
    if args.manual_csv:
        manual_rects_labeled.extend(
            _read_manual_csv(os.path.expanduser(args.manual_csv))
        )
    if args.manual_box:
        for x0, y0, w, h in args.manual_box:
            manual_rects_labeled.append((int(x0), int(y0), int(w), int(h), "manual"))

    if args.invert_manual_y and manual_rects_labeled:
        flipped: List[Tuple[int, int, int, int, str]] = []
        for x0, y0, w, h, label in manual_rects_labeled:
            y0_new = int(ny - (y0 + h))
            flipped.append((x0, y0_new, w, h, label))
        manual_rects_labeled = flipped
        print("Applied Y inversion to manual rectangles.")

    # Validate/clip manual rects to image bounds
    valid_manual_rects: List[Tuple[int, int, int, int]] = []
    for x0, y0, w, h, label in manual_rects_labeled:
        if w <= 0 or h <= 0:
            warnings.warn(
                f"[manual] Dropping non-positive size box ({x0},{y0},{w},{h})."
            )
            continue
        clipped = _clip_box_to_bounds(x0, y0, w, h, nx, ny)
        if clipped is None:
            warnings.warn(f"[manual] Dropping out-of-bounds box ({x0},{y0},{w},{h}).")
            continue
        cx0, cy0, cw, ch = clipped
        if (cx0, cy0, cw, ch) != (x0, y0, w, h):
            warnings.warn(
                f"[manual] Clipped box ({x0},{y0},{w},{h}) -> ({cx0},{cy0},{cw},{ch})."
            )
        valid_manual_rects.append((cx0, cy0, cw, ch))

    # Final list: manual first (wins visually/order), then auto, dedupe exacts
    rects = _dedupe_exact(valid_manual_rects + auto_rects)

    frac = masked_fraction(med.shape, rects)
    print(
        f"Found {len(rects)} rectangles "
        f"({len(valid_manual_rects)} manual, {len(auto_rects)} auto); "
        f"masked fraction ≈ {frac:.3%}"
    )

    # ----------------------- default output dir --------------------------
    ts = ts_utc()
    script_dir = os.path.dirname(os.path.abspath(__file__))  # typically .../scripts
    default_dir = os.path.join(script_dir, "defects", f"defects_{ts}")
    os.makedirs(default_dir, exist_ok=True)

    # ------------------------------- CSV --------------------------------
    default_csv = os.path.join(default_dir, f"nickel_defects_rects_{ts}.csv")
    csv_out = os.path.expanduser(args.csv_out) if args.csv_out else default_csv

    # Keep labels in CSV: manual vs auto
    rows = [
        dict(x0=x0, y0=y0, width=w, height=h, label="manual")
        for (x0, y0, w, h) in valid_manual_rects
    ]
    # After dedupe, avoid duplicating any exact matches in auto
    manual_set = set(valid_manual_rects)
    auto_only = [r for r in rects if r not in manual_set]
    rows += [
        dict(x0=x0, y0=y0, width=w, height=h, label="auto-flat")
        for (x0, y0, w, h) in auto_only
    ]

    pd.DataFrame(rows, columns=["x0", "y0", "width", "height", "label"]).to_csv(
        csv_out, index=False
    )
    print(f"Wrote rectangles -> {csv_out}")

    # ------------------------------- QA ---------------------------------
    qa_dir = os.path.expanduser(args.qa_dir) if args.qa_dir else default_dir
    if args.plot:
        os.makedirs(qa_dir, exist_ok=True)
        overlay_png = os.path.join(qa_dir, "overlay.png")
        mask_png = os.path.join(qa_dir, "mask.png")
        save_overlay_png(med, rects, "Median flat + defects", overlay_png)
        save_mask_png(med, rects, mask_png)
        print(f"QA images: {overlay_png}, {mask_png}")

    # ----------------------------- ingest -------------------------------
    if args.ingest:
        defects_run = args.defects_run or f"Nickel/calib/defects/{ts}"
        print(f"Ingesting defects to run: {defects_run}")
        b_write = Butler(repo, run=defects_run)

        # Register dataset type if requested
        if args.register:
            ensure_defects_dataset_type(b_write)

        # Determine detector id
        det_id: Optional[int] = args.detector
        if det_id is None:
            try:
                det_id = int(refs[0].dataId["detector"])
            except Exception:
                det_id = 0  # Nickel is single-detector
        print(f"Using detector id: {det_id}")

        boxes = rectangles_to_boxes(rects)
        defects_obj = Defects(boxes)
        dataId = dict(instrument=args.instrument, detector=det_id)

        # Write the calibration dataset
        b_write.put(defects_obj, "defects", dataId=dataId)
        print("Wrote defects dataset.")

        # Optionally certify a validity range into a calib collection
        if args.certify:
            if not (args.begin and args.end):
                raise RuntimeError("Certify requested but --begin/--end not provided.")
            import shlex
            import subprocess

            cmd = (
                f'butler certify-calibrations "{repo}" "{defects_run}" "{args.certify_to}" defects '
                f"--begin-date {args.begin} --end-date {args.end}"
            )
            print("Certifying with:", cmd)
            subprocess.run(shlex.split(cmd), check=True)
            print("Certified.")

        print("Done.")
        print("DEFECTS_RUN =", defects_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
