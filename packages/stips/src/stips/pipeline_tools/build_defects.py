#!/usr/bin/env python
"""Build rectangular sensor-defect masks from cpFlat outputs (framework tool).

Stack-side worker (runs inside the LSST environment via
``run_with_stack([... "-m", "stips.pipeline_tools.build_defects", ...])`` or the
``stips-defects-build`` console script). This is the instrument-neutral
extraction of the former ``obs-nickel-defects`` package: the *algorithm* is
framework code parameterized by the active instrument profile, while an
instrument's generated defect *products* live under its own tree (e.g.
``instruments/nickel/obs_nickel_data/``).

Algorithm (unchanged from the Nickel original)
----------------------------------------------
1. Query all ``flat`` datasets for the instrument in the given collection(s) and
   build a per-pixel **median flat**.
2. **Auto-detect** defect rectangles: Gaussian-smooth the median flat, take the
   ratio ``flat / smooth``, threshold outside ``[ratio_lo, ratio_hi]``,
   morphologically open the mask, then bound each connected component with a
   rectangle (dropping components below ``min_area`` pixels).
3. Optionally merge **manual** rectangles (repeatable ``--manual-box`` and/or a
   ``--manual-csv``), with optional Y-inversion (for a flipped detector frame),
   bounds-clipping, and exact de-duplication. Manual boxes win ordering.
4. Emit the rectangles as a CSV and/or an ECSV curated-calibration file, and/or
   ingest them into Butler as a ``defects`` calibration (optionally certifying a
   validity window into the calib chain). QA PNG overlays are optional.

Parameterization
----------------
The instrument name (Butler queries) and collection prefix (default collection
names) come from the active instrument profile (``INSTRUMENT_DIR``), overridable
with ``--instrument``. Detection thresholds are CLI arguments whose defaults are
the values that produced the current Nickel products (``--sigma 7``,
``--ratio-hi 1.10``, ``--ratio-lo 0.90``, ``--min-area 8``, ``--open 2``). The
detector id/name and raft name are CLI arguments (single-CCD generic defaults).

Producing a defect package for a NEW instrument
-----------------------------------------------
1. Build calibration flats for the instrument (``stips calibs``), then point this
   tool at that collection::

     stips-defects-build --repo $REPO --collection <cpFlat run> \
       --ecsv-out instruments/<name>/obs_<name>_data/<Prefix>/defects/ccd0/ \
       --calib-date 1970-01-01T00:00:00 --plot

   Tune ``--sigma/--ratio-hi/--ratio-lo/--min-area/--open`` to your sensor and
   add ``--manual-box X0 Y0 W H`` for defects the auto-pass misses.
2. Commit the emitted ``.ecsv`` under the instrument's curated data package and
   ``butler write-curated-calibrations $REPO <instrument-class>``.
3. Record the exact invocation + thresholds in the instrument's
   ``defects/README.md`` (see ``instruments/nickel/defects/README.md``).

Nothing here is Nickel-specific: a fork reuses this tool unchanged and only
stores its own generated ``.ecsv`` products and recipe.
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

# ------------------------------ pure helpers ---------------------------
# These carry NO ``lsst`` / matplotlib imports so ``--help`` and the unit
# tests run in a plain venv (matching build_crosstalk_calib's house style).

Rect = Tuple[int, int, int, int]
LabeledRect = Tuple[int, int, int, int, str]


def ts_utc() -> str:
    """UTC timestamp ``YYYYMMDDTHHMMSSZ`` for default output/collection names."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def detect_rectangles_from_flat(
    img,
    sigma_pix: int = 7,
    ratio_hi: float = 1.10,
    ratio_lo: float = 0.90,
    min_area_px: int = 8,
    open_kernel: int = 2,
) -> List[Rect]:
    """Return rectangles ``(x0, y0, w, h)`` indicating likely sensor defects.

    Works by smoothing + ratio thresholding + connected components. ``numpy`` and
    ``scipy.ndimage`` are imported lazily so this module imports in a plain venv.
    """
    import numpy as np
    from scipy.ndimage import binary_opening, find_objects, gaussian_filter, label

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
    rects: List[Rect] = []
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


def masked_fraction(shape: Tuple[int, int], rects: Iterable[Rect]) -> float:
    """Fraction of the ``(ny, nx)`` image covered by ``rects``."""
    import numpy as np

    mask = np.zeros(shape, dtype=bool)
    for x0, y0, w, h in rects:
        mask[y0 : y0 + h, x0 : x0 + w] = True
    return float(mask.mean())


def _clip_box_to_bounds(
    x0: int, y0: int, w: int, h: int, nx: int, ny: int
) -> Optional[Rect]:
    """Clip ``(x0,y0,w,h)`` to ``[0..nx)×[0..ny)``; return ``None`` if fully out."""
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


def _read_manual_csv(path: str) -> List[LabeledRect]:
    """Read manual boxes CSV with columns ``x0,y0,width,height[,label]``."""
    import pandas as pd

    df = pd.read_csv(path)
    for col in ("x0", "y0", "width", "height"):
        if col not in df.columns:
            raise ValueError(f"Manual CSV missing required column: {col}")
    out: List[LabeledRect] = []
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


def _dedupe_exact(rects: List[Rect]) -> List[Rect]:
    """Remove exact duplicate ``(x0,y0,w,h)`` rectangles; preserve order."""
    seen = set()
    out: List[Rect] = []
    for x0, y0, w, h in rects:
        key = (x0, y0, w, h)
        if key in seen:
            continue
        seen.add(key)
        out.append((x0, y0, w, h))
    return out


def assemble_rectangles(
    auto_rects: List[Rect],
    manual_rects_labeled: List[LabeledRect],
    nx: int,
    ny: int,
    invert_manual_y: bool = False,
) -> Tuple[List[Rect], List[Rect]]:
    """Merge manual + auto rectangles into the final defect list (pure logic).

    Applies optional Y-inversion to *manual* boxes, drops/clips out-of-bounds
    manual boxes, then returns ``(final_rects, valid_manual_rects)`` where
    ``final_rects`` = manual (first) + auto with exact duplicates removed. This
    is the unit-testable core of the mask-assembly step.
    """
    if invert_manual_y and manual_rects_labeled:
        flipped: List[LabeledRect] = []
        for x0, y0, w, h, label in manual_rects_labeled:
            y0_new = int(ny - (y0 + h))
            flipped.append((x0, y0_new, w, h, label))
        manual_rects_labeled = flipped

    valid_manual_rects: List[Rect] = []
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

    rects = _dedupe_exact(valid_manual_rects + auto_rects)
    return rects, valid_manual_rects


def generate_ecsv_content(
    rects: List[Rect],
    instrument: str,
    detector: int = 0,
    detector_name: str = "R00_S00",
    raft_name: str = "R00",
    calib_date: str = "1970-01-01T00:00:00",
) -> str:
    """Generate ECSV content for a curated ``defects`` calibration file.

    The output matches the ``obs_*_data`` curated-calibration pattern; drop the
    file at ``<data-pkg>/<Prefix>/defects/<detector-name>/<calibdate>.ecsv`` and
    ingest with ``butler write-curated-calibrations``.
    """
    now = datetime.now(timezone.utc)
    creation_date = now.strftime("%Y-%m-%d")
    creation_time = now.strftime("%H:%M:%S")
    date_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    header = f"""# %ECSV 0.9
# ---
# datatype:
# - name: x0
#   unit: pix
#   datatype: int32
#   description: X coordinate of bottom left corner of box
# - name: y0
#   unit: pix
#   datatype: int32
#   description: Y coordinate of bottom left corner of box
# - name: width
#   unit: pix
#   datatype: int32
#   description: X extent of box
# - name: height
#   unit: pix
#   datatype: int32
#   description: Y extent of box
# meta: !!omap
# - OBSTYPE: defects
# - INSTRUME: {instrument}
# - DETECTOR: {detector}
# - CALIBDATE: '{calib_date}'
# - CALIB_ID: raftName={raft_name} detectorName={detector_name} detector={detector} calibDate={calib_date} ccd={detector} ccdnum={detector} filter=None
# - DEFECTS_SCHEMA: Simple
# - DEFECTS_SCHEMA_VERSION: 1
# - DATE: '{date_iso}'
# - CALIB_CREATION_DATE: '{creation_date}'
# - CALIB_CREATION_TIME: {creation_time}
# schema: astropy-2.0
x0 y0 width height
"""

    lines = [header.rstrip()]
    for x0, y0, w, h in rects:
        lines.append(f"{x0} {y0} {w} {h}")
    return "\n".join(lines) + "\n"


def read_csv_defects(csv_path: str) -> List[Rect]:
    """Read defect rectangles from a CSV (columns ``x0,y0,width,height[,label]``)."""
    import pandas as pd

    df = pd.read_csv(csv_path)
    required = {"x0", "y0", "width", "height"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV must have columns: {required}. Found: {set(df.columns)}")
    rects: List[Rect] = []
    for _, row in df.iterrows():
        rects.append(
            (int(row["x0"]), int(row["y0"]), int(row["width"]), int(row["height"]))
        )
    return rects


def write_rects_csv(
    csv_out: str, valid_manual_rects: List[Rect], final_rects: List[Rect]
) -> None:
    """Write the labelled (manual vs auto-flat) rectangles CSV."""
    import pandas as pd

    rows = [
        dict(x0=x0, y0=y0, width=w, height=h, label="manual")
        for (x0, y0, w, h) in valid_manual_rects
    ]
    manual_set = set(valid_manual_rects)
    auto_only = [r for r in final_rects if r not in manual_set]
    rows += [
        dict(x0=x0, y0=y0, width=w, height=h, label="auto-flat")
        for (x0, y0, w, h) in auto_only
    ]
    pd.DataFrame(rows, columns=["x0", "y0", "width", "height", "label"]).to_csv(
        csv_out, index=False
    )


# --------------------------- stack-side helpers ------------------------
# lsst.* / matplotlib imports are deferred into these functions.


def _query_flat_refs(butler, instrument: str) -> list:
    """Return all flat refs available in the Butler's active collections."""
    return list(
        butler.registry.queryDatasets(
            datasetType="flat",
            where=f"instrument='{instrument}'",
            findFirst=False,
        )
    )


def median_flat(butler, instrument: str):
    """Build the per-pixel median flat; return ``(median_array, refs)``."""
    import numpy as np

    refs = _query_flat_refs(butler, instrument)
    if not refs:
        raise RuntimeError(
            "No `flat` datasets found in the given collection(s). "
            "Make sure --collection includes your cpFlat run."
        )
    arrs = [butler.get(r).image.array.astype(np.float32) for r in refs]
    return np.median(np.stack(arrs, axis=0), axis=0), refs


def rectangles_to_boxes(rects: Iterable[Rect]):
    """Convert ``(x0,y0,w,h)`` rectangles to ``lsst.geom.Box2I`` boxes."""
    from lsst.geom import Box2I, Extent2I, Point2I

    return [
        Box2I(Point2I(int(x0), int(y0)), Extent2I(int(w), int(h)))
        for x0, y0, w, h in rects
    ]


def ensure_defects_dataset_type(butler) -> None:
    """Ensure the ``defects`` DatasetType exists and is marked calibration."""
    from lsst.daf.butler import DatasetType

    dims = butler.registry.dimensions.conform({"instrument", "detector"})
    try:
        dt = butler.registry.getDatasetType("defects")
        if not getattr(dt, "isCalibration", False):
            raise RuntimeError(
                "Existing dataset type 'defects' is not marked as calibration. "
                "Create a fresh repo or choose a different dataset type name."
            )
    except Exception:
        butler.registry.registerDatasetType(
            DatasetType("defects", dims, "Defects", isCalibration=True)
        )


def _defects_class():
    """Return the ``Defects`` class from whichever stack path provides it."""
    try:
        from lsst.ip.isr import Defects  # newer stacks
    except ImportError:
        from lsst.afw.image import Defects  # older stacks
    return Defects


def save_overlay_png(img, rects: List[Rect], title: str, out_png: str) -> None:
    """QA: median flat with defect rectangles overlaid (best-effort)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.patches as patches
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"WARNING: Skipping plot {out_png} (matplotlib not available)")
        return
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


def save_mask_png(img, rects: List[Rect], out_png: str) -> None:
    """QA: binary defect mask (best-effort)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print(f"WARNING: Skipping plot {out_png} (matplotlib not available)")
        return
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


def ingest_defects(
    repo: str,
    rects: List[Rect],
    instrument: str,
    detector: int,
    defects_run: str,
    register: bool,
    certify: bool,
    begin: Optional[str],
    end: Optional[str],
    certify_to: str,
) -> None:
    """Write a ``defects`` calib to a RUN collection and optionally certify it."""
    from lsst.daf.butler import Butler

    b_write = Butler(repo, run=defects_run)
    if register:
        ensure_defects_dataset_type(b_write)

    boxes = rectangles_to_boxes(rects)
    defects_obj = _defects_class()(boxes)
    dataId = dict(instrument=instrument, detector=detector)
    b_write.put(defects_obj, "defects", dataId=dataId)
    print("Wrote defects dataset.")

    if certify:
        if not (begin and end):
            raise RuntimeError("Certify requested but --begin/--end not provided.")
        import shlex
        import subprocess

        cmd = (
            f'butler certify-calibrations "{repo}" "{defects_run}" '
            f'"{certify_to}" defects --begin-date {begin} --end-date {end}'
        )
        print("Certifying with:", cmd)
        subprocess.run(shlex.split(cmd), check=True)
        print("Certified.")


# ------------------------------- CLI -----------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Create and (optionally) ingest/export sensor defects from flats "
            "(instrument-neutral; parameterized by the active profile)."
        )
    )
    ap.add_argument(
        "--instrument",
        default=None,
        help="Instrument name for Butler queries (default: active profile name).",
    )

    # Input sources: Butler flats, and/or an existing rectangles CSV.
    ap.add_argument("--repo", default=None, help="Butler repo path")
    ap.add_argument(
        "--collection",
        default=None,
        help="Collection(s) with flats (e.g. <Prefix>/cp/.../flat/.../run)",
    )
    ap.add_argument(
        "--from-csv",
        default=None,
        help="Read rectangles from an existing CSV instead of detecting from flats.",
    )
    ap.add_argument(
        "--detector",
        type=int,
        default=None,
        help="Detector id (default: infer from flats; single-CCD=0)",
    )
    ap.add_argument(
        "--detector-name",
        default="R00_S00",
        help="Detector name for ECSV CALIB_ID (default: R00_S00)",
    )
    ap.add_argument(
        "--raft-name", default="R00", help="Raft name for ECSV CALIB_ID (default: R00)"
    )

    # Auto-detection controls (defaults = current Nickel values).
    ap.add_argument(
        "--sigma", type=int, default=7, help="Gaussian sigma (pixels) for smoothing"
    )
    ap.add_argument(
        "--ratio-hi", type=float, default=1.10, dest="ratio_hi", help="Upper ratio"
    )
    ap.add_argument(
        "--ratio-lo", type=float, default=0.90, dest="ratio_lo", help="Lower ratio"
    )
    ap.add_argument(
        "--min-area", type=int, default=8, dest="min_area", help="Min rect area (px)"
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

    # Manual rectangles.
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
        default=None,
        help="CSV with columns x0,y0,width,height[,label] for manual rectangles.",
    )
    ap.add_argument(
        "--invert-manual-y",
        action="store_true",
        help="Mirror *manual* rectangles in Y (y -> ny - (y+height)).",
    )

    # Outputs.
    ap.add_argument(
        "--csv-out",
        default=None,
        help="Path to write rectangles CSV (default: ./defects_<TS>/defects_rects_<TS>.csv)",
    )
    ap.add_argument(
        "--ecsv-out",
        default=None,
        help="Path (dir or file) to write a curated-calibration ECSV file.",
    )
    ap.add_argument(
        "--calib-date",
        default="1970-01-01T00:00:00",
        help="ECSV calibration validity date (default: 1970-01-01T00:00:00)",
    )
    ap.add_argument(
        "--plot", action="store_true", help="Write PNG overlays/masks to QA dir"
    )
    ap.add_argument("--qa-dir", default=None, help="Directory for QA PNGs")

    # Butler ingest / certify.
    ap.add_argument(
        "--ingest", action="store_true", help="Ingest defects to Butler after building"
    )
    ap.add_argument(
        "--register", action="store_true", help="Register 'defects' dataset type"
    )
    ap.add_argument(
        "--defects-run",
        default=None,
        help="Run name for ingest (default: <Prefix>/calib/defects/<TS>)",
    )
    ap.add_argument(
        "--certify", action="store_true", help="Certify validity in the calib chain"
    )
    ap.add_argument("--begin", default=None, help="Begin date (YYYY-MM-DD) for certify")
    ap.add_argument("--end", default=None, help="End date (YYYY-MM-DD) for certify")
    ap.add_argument(
        "--certify-to",
        default=None,
        help="Collection to certify into (default: <Prefix>/calib/curated)",
    )
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    # Resolve instrument name + collection prefix from the active profile (with
    # the explicit --instrument escape hatch), exactly like the other tools.
    from stips.pipeline_tools._profile_resolve import (
        resolve_collection_prefix,
        resolve_instrument_name,
    )

    instrument = resolve_instrument_name(args.instrument)
    prefix = resolve_collection_prefix(args.instrument)

    # ------------------------- gather rectangles ------------------------
    med = None
    nx = ny = None
    refs: list = []
    det_from_flats: Optional[int] = None

    if args.from_csv:
        auto_rects = read_csv_defects(os.path.expanduser(args.from_csv))
        # Bounds for manual clipping unknown without an image; use a large frame.
        nx = ny = 1 << 30
    else:
        if not args.repo or not args.collection:
            ap.error("--repo and --collection are required unless --from-csv is given")
        from lsst.daf.butler import Butler

        repo = os.path.expanduser(args.repo)
        b_flat = Butler(repo, collections=args.collection)
        print(f"Building median flat from {args.collection} ...")
        med, refs = median_flat(b_flat, instrument)
        print(f"Using {len(refs)} flat(s)")
        ny, nx = med.shape  # (rows, cols) = (y, x)
        try:
            det_from_flats = int(refs[0].dataId["detector"])
        except Exception:
            det_from_flats = 0

        auto_rects: List[Rect] = []
        if not args.no_auto:
            auto_rects = detect_rectangles_from_flat(
                med,
                sigma_pix=args.sigma,
                ratio_hi=args.ratio_hi,
                ratio_lo=args.ratio_lo,
                min_area_px=args.min_area,
                open_kernel=args.open_kernel,
            )

    # Manual rectangles.
    manual_rects_labeled: List[LabeledRect] = []
    if args.manual_csv:
        manual_rects_labeled.extend(_read_manual_csv(os.path.expanduser(args.manual_csv)))
    if args.manual_box:
        for x0, y0, w, h in args.manual_box:
            manual_rects_labeled.append((int(x0), int(y0), int(w), int(h), "manual"))

    rects, valid_manual_rects = assemble_rectangles(
        auto_rects, manual_rects_labeled, nx, ny, invert_manual_y=args.invert_manual_y
    )
    if args.invert_manual_y and manual_rects_labeled:
        print("Applied Y inversion to manual rectangles.")

    if med is not None:
        frac = masked_fraction(med.shape, rects)
        print(
            f"Found {len(rects)} rectangles "
            f"({len(valid_manual_rects)} manual, {len(auto_rects)} auto); "
            f"masked fraction ~ {frac:.3%}"
        )
    else:
        print(
            f"Found {len(rects)} rectangles "
            f"({len(valid_manual_rects)} manual, {len(auto_rects)} from CSV)"
        )

    # Resolve detector id: explicit flag > from-flats > 0.
    detector = args.detector
    if detector is None:
        detector = det_from_flats if det_from_flats is not None else 0

    # ------------------------- default output dir -----------------------
    ts = ts_utc()
    default_dir = os.path.join(os.getcwd(), f"defects_{ts}")

    # ------------------------------- CSV --------------------------------
    if args.csv_out is not None or not args.ecsv_out:
        os.makedirs(default_dir, exist_ok=True)
        default_csv = os.path.join(default_dir, f"defects_rects_{ts}.csv")
        csv_out = os.path.expanduser(args.csv_out) if args.csv_out else default_csv
        write_rects_csv(csv_out, valid_manual_rects, rects)
        print(f"Wrote rectangles -> {csv_out}")

    # ------------------------------- ECSV -------------------------------
    if args.ecsv_out:
        from pathlib import Path

        content = generate_ecsv_content(
            rects=rects,
            instrument=instrument,
            detector=detector,
            detector_name=args.detector_name,
            raft_name=args.raft_name,
            calib_date=args.calib_date,
        )
        output_path = Path(os.path.expanduser(args.ecsv_out))
        if output_path.is_dir() or not output_path.suffix:
            date_part = (
                args.calib_date.replace("-", "").replace(":", "").replace("T", "T")
            )
            output_path = output_path / f"{date_part}.ecsv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        print(f"Wrote ECSV file: {output_path}")

    # ------------------------------- QA ---------------------------------
    if args.plot and med is not None:
        qa_dir = os.path.expanduser(args.qa_dir) if args.qa_dir else default_dir
        os.makedirs(qa_dir, exist_ok=True)
        overlay_png = os.path.join(qa_dir, "overlay.png")
        mask_png = os.path.join(qa_dir, "mask.png")
        save_overlay_png(med, rects, "Median flat + defects", overlay_png)
        save_mask_png(med, rects, mask_png)
        print(f"QA images: {overlay_png}, {mask_png}")
    elif args.plot:
        print("WARNING: --plot requested but no median flat available (CSV input).")

    # ----------------------------- ingest -------------------------------
    if args.ingest:
        if not args.repo:
            ap.error("--ingest requires --repo")
        repo = os.path.expanduser(args.repo)
        defects_run = args.defects_run or f"{prefix}/calib/defects/{ts}"
        certify_to = args.certify_to or f"{prefix}/calib/curated"
        print(f"Ingesting defects to run: {defects_run}")
        print(f"Using detector id: {detector}")
        ingest_defects(
            repo=repo,
            rects=rects,
            instrument=instrument,
            detector=detector,
            defects_run=defects_run,
            register=args.register,
            certify=args.certify,
            begin=args.begin,
            end=args.end,
            certify_to=certify_to,
        )
        print("Done.")
        print("DEFECTS_RUN =", defects_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
