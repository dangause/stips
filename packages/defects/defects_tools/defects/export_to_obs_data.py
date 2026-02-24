#!/usr/bin/env python
"""
Export defects to ECSV format for obs_nickel_data curated calibrations.

This script converts defects from either:
  1. A CSV file (from make_defects_from_flats.py output)
  2. Directly from Butler flats (auto-detection)

The output is an ECSV file compatible with the LSST obs_*_data pattern for
curated calibrations. The file should be placed in:
  obs_nickel_data/Nickel/defects/{detector_name}/{calibdate}.ecsv

Example:
  obs_nickel_data/Nickel/defects/ccd0/19700101T000000.ecsv

Usage:
  # From existing CSV:
  obsn-defects-to-ecsv --csv defects.csv --output obs_nickel_data/Nickel/defects/ccd0/

  # Auto-generate from Butler flats:
  obsn-defects-to-ecsv --repo /path/to/repo --collection Nickel/cp/flat/... \
      --output obs_nickel_data/Nickel/defects/ccd0/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import pandas as pd


def generate_ecsv_content(
    rects: List[Tuple[int, int, int, int]],
    instrument: str = "Nickel",
    detector: int = 0,
    detector_name: str = "R00_S00",
    calib_date: str = "1970-01-01T00:00:00",
) -> str:
    """
    Generate ECSV content string for defects.

    Parameters
    ----------
    rects : list of (x0, y0, width, height) tuples
        Defect rectangles.
    instrument : str
        Instrument name (e.g., "Nickel").
    detector : int
        Detector ID (e.g., 0).
    detector_name : str
        Detector name (e.g., "R00_S00").
    calib_date : str
        Calibration date in ISO format (e.g., "1970-01-01T00:00:00").

    Returns
    -------
    str
        ECSV file content.
    """
    now = datetime.now(timezone.utc)
    creation_date = now.strftime("%Y-%m-%d")
    creation_time = now.strftime("%H:%M:%S")
    date_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    # Parse calib_date for CALIB_ID
    # calib_date_short = calib_date.split("T")[0]

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
# - CALIB_ID: raftName=R00 detectorName={detector_name} detector={detector} calibDate={calib_date} ccd={detector} ccdnum={detector} filter=None
# - DEFECTS_SCHEMA: Simple
# - DEFECTS_SCHEMA_VERSION: 1
# - DATE: '{date_iso}'
# - CALIB_CREATION_DATE: '{creation_date}'
# - CALIB_CREATION_TIME: {creation_time}
# schema: astropy-2.0
x0 y0 width height
"""

    # Add data rows
    lines = [header.rstrip()]
    for x0, y0, w, h in rects:
        lines.append(f"{x0} {y0} {w} {h}")

    return "\n".join(lines) + "\n"


def read_csv_defects(csv_path: str) -> List[Tuple[int, int, int, int]]:
    """
    Read defects from a CSV file.

    Expected columns: x0, y0, width, height (and optionally label).
    """
    df = pd.read_csv(csv_path)
    required = {"x0", "y0", "width", "height"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV must have columns: {required}. Found: {set(df.columns)}")

    rects = []
    for _, row in df.iterrows():
        rects.append(
            (int(row["x0"]), int(row["y0"]), int(row["width"]), int(row["height"]))
        )
    return rects


def detect_from_flats(
    repo: str,
    collection: str,
    instrument: str = "Nickel",
    sigma: int = 7,
    ratio_hi: float = 1.10,
    ratio_lo: float = 0.90,
    min_area: int = 8,
    open_kernel: int = 2,
) -> Tuple[List[Tuple[int, int, int, int]], int]:
    """
    Auto-detect defects from Butler flats.

    Returns tuple of (rectangles, detector_id).
    """
    # Import LSST dependencies only when needed
    import numpy as np
    from lsst.daf.butler import Butler
    from scipy.ndimage import binary_opening, find_objects, gaussian_filter, label

    b = Butler(repo, collections=collection)

    # Query flats
    refs = list(
        b.registry.queryDatasets(
            datasetType="flat",
            where=f"instrument='{instrument}'",
            findFirst=False,
        )
    )
    if not refs:
        raise RuntimeError(f"No flat datasets found in collection: {collection}")

    print(f"Found {len(refs)} flat(s)")

    # Build median flat
    arrs = [b.get(r).image.array.astype(np.float32) for r in refs]
    med = np.median(np.stack(arrs, axis=0), axis=0)

    # Get detector ID from first ref
    try:
        det_id = int(refs[0].dataId["detector"])
    except Exception:
        det_id = 0

    # Detect defects
    smooth = gaussian_filter(med.astype(np.float32), sigma=sigma)
    smooth = np.maximum(smooth, 1e-6)
    ratio = med / smooth

    mask = (ratio > ratio_hi) | (ratio < ratio_lo)
    if open_kernel > 0:
        mask = binary_opening(
            mask, structure=np.ones((open_kernel, open_kernel), dtype=bool)
        )

    labels, _ = label(mask)
    rects = []
    for sl in find_objects(labels):
        if sl is None:
            continue
        ys, xs = sl
        h = int(ys.stop - ys.start)
        w = int(xs.stop - xs.start)
        if w * h < min_area:
            continue
        rects.append((int(xs.start), int(ys.start), w, h))

    return rects, det_id


def main():
    ap = argparse.ArgumentParser(
        description="Export defects to ECSV format for obs_nickel_data."
    )

    # Input source (one required)
    input_group = ap.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--csv",
        help="Path to CSV file with defects (from obsn-defects-from-flats)",
    )
    input_group.add_argument(
        "--repo",
        help="Butler repo path (for auto-detection from flats)",
    )

    # Butler options (only with --repo)
    ap.add_argument(
        "--collection",
        help="Collection with flats (required with --repo)",
    )

    # Output
    ap.add_argument(
        "--output",
        required=True,
        help="Output directory or file path. If directory, filename is auto-generated.",
    )

    # Calibration metadata
    ap.add_argument(
        "--calib-date",
        default="1970-01-01T00:00:00",
        help="Calibration validity date (default: 1970-01-01T00:00:00 for all-time validity)",
    )
    ap.add_argument(
        "--instrument",
        default="Nickel",
        help="Instrument name (default: Nickel)",
    )
    ap.add_argument(
        "--detector",
        type=int,
        default=0,
        help="Detector ID (default: 0)",
    )
    ap.add_argument(
        "--detector-name",
        default="R00_S00",
        help="Detector name (default: R00_S00)",
    )

    # Auto-detection parameters (only with --repo)
    ap.add_argument("--sigma", type=int, default=7, help="Gaussian sigma for smoothing")
    ap.add_argument(
        "--ratio-hi", type=float, default=1.10, help="Upper ratio threshold"
    )
    ap.add_argument(
        "--ratio-lo", type=float, default=0.90, help="Lower ratio threshold"
    )
    ap.add_argument("--min-area", type=int, default=8, help="Minimum rectangle area")
    ap.add_argument(
        "--open", type=int, default=2, dest="open_kernel", help="Opening kernel size"
    )

    args = ap.parse_args()

    # Validate Butler options
    if args.repo and not args.collection:
        ap.error("--collection is required when using --repo")

    # Get defects
    if args.csv:
        print(f"Reading defects from CSV: {args.csv}")
        rects = read_csv_defects(args.csv)
        det_id = args.detector
    else:
        print(f"Auto-detecting defects from Butler repo: {args.repo}")
        rects, det_id = detect_from_flats(
            repo=args.repo,
            collection=args.collection,
            instrument=args.instrument,
            sigma=args.sigma,
            ratio_hi=args.ratio_hi,
            ratio_lo=args.ratio_lo,
            min_area=args.min_area,
            open_kernel=args.open_kernel,
        )
        if args.detector != 0:
            det_id = args.detector

    print(f"Found {len(rects)} defect rectangles")

    # Generate ECSV content
    content = generate_ecsv_content(
        rects=rects,
        instrument=args.instrument,
        detector=det_id,
        detector_name=args.detector_name,
        calib_date=args.calib_date,
    )

    # Determine output path
    output_path = Path(args.output)
    if output_path.is_dir() or not output_path.suffix:
        # Generate filename from calib date
        date_part = args.calib_date.replace("-", "").replace(":", "").replace("T", "T")
        # Convert to YYYYMMDDTHHMMSS format
        date_part = date_part.replace("-", "")
        filename = f"{date_part}.ecsv"
        output_path = output_path / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    output_path.write_text(content)
    print(f"Wrote ECSV file: {output_path}")

    # Print usage hint
    print()
    print("To use this file in obs_nickel_data:")
    print(
        f"  1. Place the file at: obs_nickel_data/Nickel/defects/ccd0/{output_path.name}"
    )
    print(
        "  2. Run: butler write-curated-calibrations $REPO Nickel $RAW_RUN --collection $CURATED_RUN"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
