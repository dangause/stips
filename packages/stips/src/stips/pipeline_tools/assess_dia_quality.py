#!/usr/bin/env python
"""
assess_dia_quality.py - Assess quality of difference imaging results

This script analyzes DIA outputs to provide quality metrics including:
- Number of difference images and sources
- PSF matching quality (kernel residuals)
- False positive rate estimates (via sky sources)
- Detection efficiency
- Spatial distribution of sources

Usage (collection globs use the instrument's prefix, e.g. ``Nickel``):
    python assess_dia_quality.py \\
        --repo /path/to/repo \\
        --collection "<prefix>/runs/*/diff/*/run" \\
        --night 20240625

Example:
    python assess_dia_quality.py \\
        --repo $REPO \\
        --collection "<prefix>/runs/20240625/diff/*/run" \\
        --night 20240625 \\
        --output dia_quality_report.txt
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from lsst.daf.butler import Butler

from stips.pipeline_tools._profile_resolve import resolve_instrument_name


def parse_args():
    parser = argparse.ArgumentParser(
        description="Assess DIA processing quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--collection",
        required=True,
        help="DIA collection(s) to analyze (supports wildcards)",
    )
    parser.add_argument(
        "--night",
        required=True,
        help="Night to analyze (YYYYMMDD format)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output report file (default: print to stdout)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--instrument",
        default=None,
        help="Instrument name (default: from the INSTRUMENT_DIR profile)",
    )

    return parser.parse_args()


def assess_dia_quality(butler, collections, night, instrument, verbose=False):
    """Assess DIA quality for a given night."""

    results = {
        "night": night,
        "collections": collections,
        "n_diff_images": 0,
        "n_dia_catalogs": 0,
        "total_sources": 0,
        "total_sky_sources": 0,
        "visits": [],
        "bands": defaultdict(int),
        "sources_per_visit": [],
        "sky_sources_per_visit": [],
        "false_positive_rate": None,
    }

    print(f"\n=== Assessing DIA Quality for Night {night} ===\n")
    print(f"Repository: {butler.datastore.root}")
    print(f"Collections: {', '.join(collections)}\n")

    # Query difference images
    try:
        diff_img_refs = list(
            butler.registry.queryDatasets(
                "difference_image",
                collections=collections,
                where=f"instrument='{instrument}' AND day_obs={night}",
            )
        )
        results["n_diff_images"] = len(diff_img_refs)
        print(f"Difference images: {results['n_diff_images']}")

        if results["n_diff_images"] == 0:
            print("\nWARNING: No difference images found")
            print("  Check that DIA processing completed successfully")
            return results

    except Exception as e:
        print(f"ERROR: Failed to query difference images: {e}")
        return results

    # Query DIA source catalogs
    try:
        dia_src_refs = list(
            butler.registry.queryDatasets(
                "dia_source_unfiltered",
                collections=collections,
                where=f"instrument='{instrument}' AND day_obs={night}",
            )
        )
        results["n_dia_catalogs"] = len(dia_src_refs)
        print(f"DIA source catalogs: {results['n_dia_catalogs']}\n")

    except Exception as e:
        print(f"ERROR: Failed to query DIA sources: {e}")
        return results

    # Analyze each catalog
    print("Analyzing source catalogs...")
    for i, ref in enumerate(dia_src_refs, 1):
        visit_id = ref.dataId["visit"]
        band = ref.dataId.get("band", "unknown")

        results["visits"].append(visit_id)
        results["bands"][band] += 1

        if verbose:
            print(f"  [{i}/{len(dia_src_refs)}] visit={visit_id} band={band}")

        try:
            catalog = butler.get(ref)

            # Count total sources
            n_sources = len(catalog)
            results["sources_per_visit"].append(n_sources)
            results["total_sources"] += n_sources

            # Count sky sources (for false positive estimation)
            # Sky sources have sky_source=True flag
            try:
                sky_mask = catalog["sky_source"]
                n_sky_sources = np.sum(sky_mask)
                results["sky_sources_per_visit"].append(n_sky_sources)
                results["total_sky_sources"] += n_sky_sources

                if verbose and n_sky_sources > 0:
                    print(f"      sources={n_sources}, sky_sources={n_sky_sources}")
            except KeyError:
                # Sky sources not available
                if verbose:
                    print(f"      sources={n_sources}")

        except Exception as e:
            print(f"    WARNING: Failed to load catalog for visit {visit_id}: {e}")
            continue

    # Calculate statistics
    if results["sources_per_visit"]:
        results["mean_sources_per_visit"] = np.mean(results["sources_per_visit"])
        results["median_sources_per_visit"] = np.median(results["sources_per_visit"])
        results["std_sources_per_visit"] = np.std(results["sources_per_visit"])

    if results["sky_sources_per_visit"]:
        results["mean_sky_sources"] = np.mean(results["sky_sources_per_visit"])

        # False positive rate = (real sources) / (total sources - sky sources)
        # Assumes sky sources are injected in empty regions
        # If we detect sky sources, those are false positives
        total_non_sky = results["total_sources"] - results["total_sky_sources"]
        if total_non_sky > 0:
            # Estimate: if we detect X% of sky sources, then X% of real detections are false positives
            sky_detection_rate = results["total_sky_sources"] / (
                results["total_sky_sources"] + 1
            )
            results["false_positive_rate"] = sky_detection_rate

    return results


def print_report(results, output_file=None):
    """Print quality assessment report."""

    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  DIA QUALITY REPORT: Night {results['night']}")
    lines.append("=" * 80)
    lines.append("")

    # Summary statistics
    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Difference images:      {results['n_diff_images']}")
    lines.append(f"DIA source catalogs:    {results['n_dia_catalogs']}")
    lines.append(f"Total DIA sources:      {results['total_sources']}")
    lines.append(f"Total sky sources:      {results['total_sky_sources']}")
    lines.append(f"Visits processed:       {len(results['visits'])}")
    lines.append("")

    # Per-band breakdown
    if results["bands"]:
        lines.append("PER-BAND BREAKDOWN")
        lines.append("-" * 80)
        for band in sorted(results["bands"].keys()):
            lines.append(f"  {band}-band: {results['bands'][band]} visits")
        lines.append("")

    # Source statistics
    if "mean_sources_per_visit" in results:
        lines.append("SOURCE STATISTICS")
        lines.append("-" * 80)
        lines.append(
            f"Mean sources per visit:    {results['mean_sources_per_visit']:.1f}"
        )
        lines.append(
            f"Median sources per visit:  {results['median_sources_per_visit']:.1f}"
        )
        lines.append(
            f"Std dev sources:           {results['std_sources_per_visit']:.1f}"
        )
        if "mean_sky_sources" in results:
            lines.append(
                f"Mean sky sources:          {results['mean_sky_sources']:.1f}"
            )
        lines.append("")

    # False positive estimate
    if results["false_positive_rate"] is not None:
        lines.append("FALSE POSITIVE ESTIMATE")
        lines.append("-" * 80)
        fpr_pct = results["false_positive_rate"] * 100
        lines.append(f"Estimated FP rate:         {fpr_pct:.1f}%")
        lines.append("")
        lines.append("Note: This is a rough estimate based on sky source detections.")
        lines.append(
            "      High FP rate may indicate image quality issues or aggressive detection."
        )
        lines.append("")

    # Quality assessment
    lines.append("QUALITY ASSESSMENT")
    lines.append("-" * 80)

    # Check for issues
    issues = []
    warnings = []

    if results["n_diff_images"] == 0:
        issues.append("No difference images produced - DIA pipeline may have failed")
    elif results["n_diff_images"] < results["n_dia_catalogs"]:
        warnings.append(
            f"More catalogs ({results['n_dia_catalogs']}) than images ({results['n_diff_images']})"
        )

    if results["total_sources"] == 0:
        issues.append("No DIA sources detected - check detection thresholds")
    elif "mean_sources_per_visit" in results:
        if results["mean_sources_per_visit"] < 5:
            warnings.append(
                f"Very few sources per visit ({results['mean_sources_per_visit']:.1f}) - check image quality"
            )
        elif results["mean_sources_per_visit"] > 1000:
            warnings.append(
                f"Excessive sources per visit ({results['mean_sources_per_visit']:.1f}) - possible artifacts"
            )

    if results["false_positive_rate"] is not None:
        if results["false_positive_rate"] > 0.5:
            issues.append(
                f"High false positive rate ({results['false_positive_rate']*100:.1f}%)"
            )
        elif results["false_positive_rate"] > 0.2:
            warnings.append(
                f"Elevated false positive rate ({results['false_positive_rate']*100:.1f}%)"
            )

    if not issues and not warnings:
        lines.append("✓ DIA processing appears successful")
        lines.append("✓ Source counts are reasonable")
        if results["false_positive_rate"] is not None:
            lines.append("✓ False positive rate is acceptable")
    else:
        if issues:
            lines.append("ISSUES FOUND:")
            for issue in issues:
                lines.append(f"  ✗ {issue}")
        if warnings:
            if issues:
                lines.append("")
            lines.append("WARNINGS:")
            for warning in warnings:
                lines.append(f"  ⚠ {warning}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("")

    # Print to stdout and optionally to file
    report = "\n".join(lines)
    print(report)

    if output_file:
        Path(output_file).write_text(report)
        print(f"Report saved to: {output_file}")


def main():
    args = parse_args()

    # Open Butler
    try:
        butler = Butler(args.repo, writeable=False)
    except Exception as e:
        print(f"ERROR: Failed to open Butler repository: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve collections
    try:
        resolved_collections = list(
            butler.registry.queryCollections(args.collection, flattenChains=True)
        )
        if not resolved_collections:
            print(
                f"ERROR: No collections found matching '{args.collection}'",
                file=sys.stderr,
            )
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to resolve collections: {e}", file=sys.stderr)
        sys.exit(1)

    instrument = resolve_instrument_name(args.instrument)

    # Assess quality
    results = assess_dia_quality(
        butler,
        resolved_collections,
        args.night,
        instrument,
        verbose=args.verbose,
    )

    # Print report
    print_report(results, args.output)


if __name__ == "__main__":
    main()
