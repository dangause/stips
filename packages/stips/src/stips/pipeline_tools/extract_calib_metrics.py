#!/usr/bin/env python
"""
extract_calib_metrics.py - Extract astrometric and photometric calibration metrics

Dumps per-visit/per-detector calibration metrics to CSV for paper tables and
quality plots. Pulls from three butler dataset groups:

  1. preliminary_visit_summary      -> astromOffsetMean/Std, zeroPoint, psfSigma,
                                       skyBg, skyNoise, nPsfStar, photoCalib
  2. calibrateImage_metadata_metrics -> astrometry_matches_count,
                                        photometry_matches_count, star_count,
                                        psf_good_star_count, final_psf_sigma
                                        (only if the visit-quality pipeline was run)
  3. single_visit_star_ref_match_{astrom,photom}_metrics -> aggregated
                                        refcat-residual RMS/bias (optional)

Usage (collection globs use the instrument's prefix, e.g. ``Nickel``):
    extract-calib-metrics \\
        --repo $REPO \\
        --collection "<prefix>/runs/20230519/processCcd/*" \\
        --night 20230519 \\
        --output calib_metrics_20230519.csv

    # Combine across many nights using a glob:
    extract-calib-metrics \\
        --repo $REPO \\
        --collection "<prefix>/runs/*/processCcd/*" \\
        --output calib_metrics_all.csv

    # Include analysis_tools refcat-residual metrics (must be produced upstream):
    extract-calib-metrics \\
        --repo $REPO \\
        --collection "<prefix>/runs/20230519/processCcd/*" \\
        --include-refcat-metrics \\
        --output calib_metrics_20230519.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from lsst.daf.butler import Butler
from lsst.daf.butler.registry import MissingDatasetTypeError

from stips.core.config import load_active_profile


def _resolve_instrument(instrument: str | None) -> str:
    """Resolve the instrument name from a CLI arg or the active profile.

    Stays robust if the obs package is not importable (falls back to "Nickel").
    """
    if instrument:
        return instrument
    try:
        return load_active_profile().name
    except Exception:
        return "Nickel"


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

VISIT_SUMMARY_COLUMNS = [
    "visit",
    "detector",
    "band",
    "physical_filter",
    "ra",
    "dec",
    "zenithDistance",
    "zeroPoint",
    "skyBg",
    "skyNoise",
    "psfSigma",
    "psfArea",
    "nPsfStar",
    "astromOffsetMean",
    "astromOffsetStd",
    "expTime",
]

METADATA_METRIC_NAMES = [
    "astrometry_matches_count",
    "photometry_matches_count",
    "matched_psf_star_count",
    "psf_available_star_count",
    "psf_good_star_count",
    "final_psf_sigma",
    "star_count",
    "saturated_source_count",
    "cosmic_ray_count",
]


def _extract_measurements(bundle) -> dict[str, float]:
    """Flatten a MetricMeasurementBundle (or dict-like) to {short_name: value}.

    analysis_tools bundles are typically Dict[str, list[Measurement]] keyed by
    the atool/action name, where each Measurement has .metric_name and .quantity.
    Be defensive across stack versions: handle dict-of-list, dict-of-Measurement,
    or a plain iterable of Measurements.
    """
    out: dict[str, float] = {}

    def _record(meas) -> None:
        name = getattr(meas, "metric_name", None)
        if name is None:
            return
        short = str(name).split(".")[-1]
        q = getattr(meas, "quantity", None)
        if q is None:
            return
        try:
            out[short] = float(getattr(q, "value", q))
        except (TypeError, ValueError):
            pass

    # Dict-like: iterate items
    if hasattr(bundle, "items"):
        try:
            for _key, val in bundle.items():
                if isinstance(val, (list, tuple)):
                    for meas in val:
                        _record(meas)
                else:
                    _record(val)
            if out:
                return out
        except Exception:
            pass

    # Iterable of Measurement objects
    try:
        for meas in bundle:
            if hasattr(meas, "metric_name"):
                _record(meas)
    except TypeError:
        pass

    return out


# ---------------------------------------------------------------------------
# Butler queries
# ---------------------------------------------------------------------------


def _resolve_collections(butler: Butler, pattern: str) -> list[str]:
    """Expand a collection glob into a concrete ordered list.

    findFirst=True in queryDatasets requires resolved collection names.
    Reverse-sort so the most recent timestamp wins for the CHAINED parents.
    """
    resolved = sorted(
        butler.registry.queryCollections(
            pattern,
            includeChains=True,
        ),
        reverse=True,
    )
    return list(resolved)


def query_visit_summary(
    butler: Butler, collection: str, night: str | None, instrument: str
):
    """Yield per-detector rows from preliminary_visit_summary datasets."""
    where = f"instrument='{instrument}'"
    if night:
        where += f" AND exposure.day_obs = {int(night)}"

    collections = _resolve_collections(butler, collection)
    if not collections:
        print(
            f"[warn] no collections match pattern {collection!r}",
            file=sys.stderr,
        )
        return
    print(
        f"[info] resolved {len(collections)} collection(s) from pattern",
        file=sys.stderr,
    )

    try:
        refs = list(
            butler.registry.queryDatasets(
                "preliminary_visit_summary",
                collections=collections,
                where=where,
                findFirst=True,
            )
        )
    except MissingDatasetTypeError:
        print(
            "[warn] dataset type 'preliminary_visit_summary' not registered in repo",
            file=sys.stderr,
        )
        return

    if not refs:
        print(
            f"[warn] no preliminary_visit_summary datasets in {collection} "
            f"(night={night})",
            file=sys.stderr,
        )
        return

    for ref in refs:
        try:
            table = butler.get(ref)
        except Exception as exc:  # pragma: no cover - defensive I/O
            print(f"[warn] failed to load {ref}: {exc}", file=sys.stderr)
            continue

        visit = ref.dataId["visit"]

        # Expand dataId to get the real day_obs from the visit dimension record
        expanded = butler.registry.expandDataId(ref.dataId)
        day_obs = expanded.records["visit"].day_obs

        for row in table:
            out = {"visit": visit}
            # Set detector from dataId (Nickel is single-detector; default 0)
            out["detector"] = ref.dataId.get("detector", 0)
            # Set day_obs from the visit dimension record (int, YYYYMMDD)
            out["day_obs"] = int(day_obs)
            for col in VISIT_SUMMARY_COLUMNS:
                if col in ("visit", "detector"):
                    continue
                try:
                    val = row[col]
                except (KeyError, ValueError):
                    val = None
                out[col] = _coerce(val)
            yield out


def query_metadata_metrics(
    butler: Butler, collection: str, night: str | None, instrument: str
):
    """Return {(visit, detector): {metric: value}} from calibrateImage_metadata_metrics."""
    out: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)

    where = f"instrument='{instrument}'"
    if night:
        where += f" AND exposure.day_obs = {int(night)}"

    collections = _resolve_collections(butler, collection)
    if not collections:
        return out

    try:
        refs = list(
            butler.registry.queryDatasets(
                "calibrateImage_metadata_metrics",
                collections=collections,
                where=where,
                findFirst=True,
            )
        )
    except MissingDatasetTypeError:
        return out

    for ref in refs:
        try:
            metrics = butler.get(ref)
        except Exception as exc:
            print(f"[warn] failed to load {ref}: {exc}", file=sys.stderr)
            continue

        visit = ref.dataId["visit"]
        detector = ref.dataId["detector"]
        extracted = _extract_measurements(metrics)
        row = {k: v for k, v in extracted.items() if k in METADATA_METRIC_NAMES}
        if row:
            out[(visit, detector)] = row

    return out


def query_refcat_residual_metrics(
    butler: Butler, collection: str, night: str | None, instrument: str
):
    """Return {(visit, detector): {metric: value}} from refcat-residual metric bundles."""
    out: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)

    where = f"instrument='{instrument}'"
    if night:
        where += f" AND exposure.day_obs = {int(night)}"

    collections = _resolve_collections(butler, collection)
    if not collections:
        return out

    for dataset_type, prefix in (
        ("single_visit_star_ref_match_astrom_metrics", "astrom"),
        ("single_visit_star_ref_match_photom_metrics", "photom"),
    ):
        try:
            refs = list(
                butler.registry.queryDatasets(
                    dataset_type,
                    collections=collections,
                    where=where,
                    findFirst=True,
                )
            )
        except MissingDatasetTypeError:
            print(
                f"[info] dataset type '{dataset_type}' not present — "
                "re-run with the visit-quality analysis pipeline to populate",
                file=sys.stderr,
            )
            continue

        for ref in refs:
            try:
                metrics = butler.get(ref)
            except Exception as exc:
                print(f"[warn] failed to load {ref}: {exc}", file=sys.stderr)
                continue

            visit = ref.dataId.get("visit")
            detector = ref.dataId.get("detector", -1)
            extracted = _extract_measurements(metrics)
            for short, val in extracted.items():
                out[(visit, detector)][f"{prefix}_{short}"] = val

    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce(value):
    """Convert numpy / afw values to plain Python scalars for CSV."""
    if value is None:
        return None
    try:
        import numpy as np

        if isinstance(value, (np.floating, np.integer)):
            v = value.item()
            if isinstance(v, float) and (v != v):  # NaN
                return None
            return v
        if isinstance(value, np.ndarray) and value.size == 1:
            return _coerce(value.item())
    except Exception:
        pass
    if hasattr(value, "asDegrees"):
        try:
            return value.asDegrees()
        except Exception:
            pass
    return value


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract per-visit astrometric/photometric calibration metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--collection",
        required=True,
        help="Collection(s) to query (wildcards ok, e.g. '<prefix>/runs/*/processCcd/*')",
    )
    parser.add_argument(
        "--night",
        help="Observing night YYYYMMDD (filters by exposure.day_obs). "
        "If omitted, all nights in the collection are included.",
    )
    parser.add_argument(
        "--include-refcat-metrics",
        action="store_true",
        help="Also pull single_visit_star_ref_match_{astrom,photom}_metrics "
        "(requires visit-quality analysis pipeline to have been run)",
    )
    parser.add_argument("--output", "-o", required=True, help="Output CSV path")
    parser.add_argument(
        "--instrument",
        default=None,
        help="Instrument name (default: from the INSTRUMENT_DIR profile)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    butler = Butler(args.repo)

    instrument = _resolve_instrument(args.instrument)

    print(f"[info] querying collection: {args.collection}", file=sys.stderr)
    if args.night:
        print(f"[info] filtering to day_obs={args.night}", file=sys.stderr)

    # Primary: visit summary
    rows = list(query_visit_summary(butler, args.collection, args.night, instrument))
    print(f"[info] loaded {len(rows)} visit_summary rows", file=sys.stderr)

    # Secondary: task metadata metrics
    metadata = query_metadata_metrics(butler, args.collection, args.night, instrument)
    if metadata:
        print(
            f"[info] loaded calibrateImage_metadata_metrics for "
            f"{len(metadata)} (visit, detector) pairs",
            file=sys.stderr,
        )
    else:
        print(
            "[info] no calibrateImage_metadata_metrics found "
            "(visit-quality pipeline not run on these collections)",
            file=sys.stderr,
        )

    # Tertiary: refcat residual metrics
    refcat = {}
    if args.include_refcat_metrics:
        refcat = query_refcat_residual_metrics(
            butler, args.collection, args.night, instrument
        )
        if refcat:
            print(
                f"[info] loaded refcat residual metrics for " f"{len(refcat)} entries",
                file=sys.stderr,
            )

    # Merge
    metric_keys: set[str] = set()
    merged_rows = []
    for row in rows:
        key = (row["visit"], row["detector"])
        if key in metadata:
            for k, v in metadata[key].items():
                row[k] = v
                metric_keys.add(k)
        if key in refcat:
            for k, v in refcat[key].items():
                row[k] = v
                metric_keys.add(k)
        merged_rows.append(row)

    if not merged_rows:
        print(
            "[error] no rows to write. Check --collection and --night.",
            file=sys.stderr,
        )
        return 1

    # Build column order
    base_cols = ["day_obs"] + VISIT_SUMMARY_COLUMNS
    extra_cols = sorted(metric_keys)
    columns = base_cols + extra_cols

    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in merged_rows:
            writer.writerow(row)

    print(
        f"[ok] wrote {len(merged_rows)} rows x {len(columns)} cols -> {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
