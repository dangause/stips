#!/usr/bin/env python3
"""Inspect and explore Butler repository contents.

This tool provides exploratory data analysis for Butler repositories:
- Collection hierarchy and structure
- Dataset inventory and statistics
- Calibration status and coverage
- Template availability and characteristics

Usage:
  obsn-eda-butler collections --repo /path/to/repo [--pattern "Nickel/*"]
  obsn-eda-butler datasets --repo /path/to/repo --collection "Nickel/runs/*/processCcd/*/run"
  obsn-eda-butler calibs --repo /path/to/repo [--nights 20200101,20200102,...]
  obsn-eda-butler templates --repo /path/to/repo [--band r]

Environment:
  REPO    Butler repository path (can be used instead of --repo)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import defaultdict
from typing import Any

from . import formatters

try:
    from lsst.daf.butler import Butler
except ImportError:
    Butler = None


def _ensure_butler():
    """Check that Butler is available."""
    if Butler is None:
        formatters.print_error(
            "lsst.daf.butler not available. "
            "Ensure LSST Science Pipelines is installed and activated."
        )
        sys.exit(1)


def cmd_collections(args) -> int:
    """Show collection hierarchy and structure."""
    _ensure_butler()

    try:
        butler = Butler(args.repo, writeable=False)
    except Exception as err:
        formatters.print_error(f"Failed to open Butler repository: {err}")
        return 1

    formatters.print_section("Butler Collections")
    formatters.print_info("Repository", args.repo)

    # Get all collections
    try:
        all_collections = list(butler.registry.queryCollections())
    except Exception as err:
        formatters.print_error(f"Failed to query collections: {err}")
        return 1

    if not all_collections:
        formatters.print_warning("No collections found in repository")
        return 1

    # Filter by pattern if specified
    if args.pattern:
        import fnmatch

        all_collections = [
            c for c in all_collections if fnmatch.fnmatch(c, args.pattern)
        ]

    if not all_collections:
        formatters.print_warning(f"No collections match pattern: {args.pattern}")
        return 1

    # Categorize collections
    categories = {
        "Raw": [],
        "Calibrations": [],
        "Templates": [],
        "Processing Runs": [],
        "Reference Catalogs": [],
        "Chains": [],
        "Other": [],
    }

    for coll in sorted(all_collections):
        coll_str = str(coll)
        # Determine collection type
        try:
            coll_type = butler.registry.getCollectionType(coll)
            is_chain = "CHAIN" in str(coll_type)
        except Exception:
            is_chain = False

        if is_chain:
            categories["Chains"].append(coll_str)
        elif "raw" in coll_str.lower():
            categories["Raw"].append(coll_str)
        elif "calib" in coll_str.lower() or "/cp/" in coll_str:
            categories["Calibrations"].append(coll_str)
        elif "template" in coll_str.lower():
            categories["Templates"].append(coll_str)
        elif "refcat" in coll_str.lower() or "monster" in coll_str.lower():
            categories["Reference Catalogs"].append(coll_str)
        elif "/runs/" in coll_str or "/diff/" in coll_str:
            categories["Processing Runs"].append(coll_str)
        else:
            categories["Other"].append(coll_str)

    # Display categorized collections
    for category, colls in categories.items():
        if colls:
            formatters.print_section(
                f"{category} Collections ({len(colls)})", style="bold blue"
            )
            for coll in colls:
                # Try to get collection info
                try:
                    coll_type = butler.registry.getCollectionType(coll)
                    type_str = str(coll_type).split(".")[-1]
                except Exception:
                    type_str = "UNKNOWN"

                print(f"  [{type_str}] {coll}")

    # Output as structured data if requested
    if args.format != "table":
        output_data = []
        for coll in sorted(all_collections):
            try:
                coll_type = butler.registry.getCollectionType(coll)
                type_str = str(coll_type).split(".")[-1]
            except Exception:
                type_str = "UNKNOWN"

            output_data.append(
                {
                    "collection": str(coll),
                    "type": type_str,
                }
            )

        formatters.output_data(
            output_data,
            format_type=args.format,
            output_file=args.output,
            column_order=["collection", "type"],
        )

    return 0


def cmd_datasets(args) -> int:
    """Show dataset inventory and statistics."""
    _ensure_butler()

    try:
        butler = Butler(args.repo, writeable=False)
    except Exception as err:
        formatters.print_error(f"Failed to open Butler repository: {err}")
        return 1

    formatters.print_section("Dataset Inventory")
    formatters.print_info("Repository", args.repo)
    formatters.print_info("Collection", args.collection)

    # Get dataset types
    try:
        dataset_types = list(butler.registry.queryDatasetTypes())
    except Exception as err:
        formatters.print_error(f"Failed to query dataset types: {err}")
        return 1

    formatters.print_info("Total dataset types", len(dataset_types))

    # Count datasets by type in the specified collection
    dataset_counts: dict[str, int] = {}

    for dt in dataset_types:
        try:
            refs = list(butler.registry.queryDatasets(dt, collections=args.collection))
            if refs:
                dataset_counts[dt.name] = len(refs)
        except Exception:
            # Some dataset types may not exist in this collection
            continue

    if not dataset_counts:
        formatters.print_warning(f"No datasets found in collection: {args.collection}")
        return 1

    # Prepare table data
    table_data = []
    for dataset_name, count in sorted(
        dataset_counts.items(), key=lambda x: x[1], reverse=True
    ):
        table_data.append(
            {
                "Dataset_Type": dataset_name,
                "Count": count,
            }
        )

    formatters.output_data(
        table_data,
        format_type=args.format,
        output_file=args.output,
        title=f"Datasets in {args.collection}",
        column_order=["Dataset_Type", "Count"],
    )

    return 0


def cmd_calibs(args) -> int:
    """Show calibration status and coverage."""
    _ensure_butler()

    try:
        butler = Butler(args.repo, writeable=False)
    except Exception as err:
        formatters.print_error(f"Failed to open Butler repository: {err}")
        return 1

    formatters.print_section("Calibration Coverage")
    formatters.print_info("Repository", args.repo)

    # Determine nights to check
    if args.nights:
        nights = [n.strip() for n in args.nights.split(",")]
    else:
        # Try to find nights from raw collections
        try:
            raw_collections = [
                c for c in butler.registry.queryCollections() if "raw" in str(c).lower()
            ]
            nights = set()
            for coll in raw_collections:
                # Extract YYYYMMDD from collection name
                match = re.search(r"(\d{8})", str(coll))
                if match:
                    nights.add(match.group(1))
            nights = sorted(nights)
        except Exception:
            nights = []

    if not nights:
        formatters.print_warning("No nights specified and none found in repository")
        return 1

    # Check calibration types
    calib_types = ["bias", "flat", "dark"]  # Standard calibration types

    # Build table
    table_data = []
    for night in nights:
        row: dict[str, Any] = {"Night": night}

        # Check for calibration collections for this night
        calib_collections = [
            c
            for c in butler.registry.queryCollections()
            if night in str(c) and any(ct in str(c).lower() for ct in calib_types)
        ]

        # Count each calibration type
        for calib_type in calib_types:
            matching_colls = [
                c for c in calib_collections if calib_type in str(c).lower()
            ]
            if matching_colls:
                # Try to count datasets
                try:
                    # Look for combined calibrations
                    dataset_name = calib_type  # e.g., "bias", "flat"
                    refs = list(
                        butler.registry.queryDatasets(
                            dataset_name,
                            collections=matching_colls,
                        )
                    )
                    row[calib_type.capitalize()] = len(refs) if refs else "✗"
                except Exception:
                    row[calib_type.capitalize()] = "?"
            else:
                row[calib_type.capitalize()] = "✗"

        # Check for defects
        defect_colls = [
            c for c in butler.registry.queryCollections() if "defect" in str(c).lower()
        ]
        try:
            defect_refs = list(
                butler.registry.queryDatasets("defects", collections=defect_colls)
            )
            row["Defects"] = "✓" if defect_refs else "✗"
        except Exception:
            row["Defects"] = "?"

        table_data.append(row)

    column_order = ["Night"] + [ct.capitalize() for ct in calib_types] + ["Defects"]

    formatters.output_data(
        table_data,
        format_type=args.format,
        output_file=args.output,
        title="Calibration Coverage by Night",
        column_order=column_order,
    )

    return 0


def cmd_templates(args) -> int:
    """Show template availability and characteristics."""
    _ensure_butler()

    try:
        butler = Butler(args.repo, writeable=False)
    except Exception as err:
        formatters.print_error(f"Failed to open Butler repository: {err}")
        return 1

    formatters.print_section("Template Coverage")
    formatters.print_info("Repository", args.repo)

    # Find template collections
    try:
        template_collections = [
            c
            for c in butler.registry.queryCollections()
            if "template" in str(c).lower()
        ]
    except Exception as err:
        formatters.print_error(f"Failed to query collections: {err}")
        return 1

    if not template_collections:
        formatters.print_warning("No template collections found")
        return 1

    formatters.print_info("Template collections found", len(template_collections))

    # Query for deepCoadd or template images
    template_dataset_types = ["deepCoadd", "goodSeeingCoadd", "templateCoadd"]

    templates_by_tract_band: dict[tuple[int, str], dict] = defaultdict(
        lambda: {
            "patches": set(),
            "collections": set(),
            "dataset_type": None,
        }
    )

    for dt_name in template_dataset_types:
        try:
            refs = butler.registry.queryDatasets(
                dt_name,
                collections=template_collections,
            )

            for ref in refs:
                # Extract tract and band from data ID
                data_id = ref.dataId
                tract = data_id.get("tract")
                band = data_id.get("band")
                patch = data_id.get("patch")

                if tract is not None and band:
                    key = (tract, band)
                    templates_by_tract_band[key]["dataset_type"] = dt_name
                    templates_by_tract_band[key]["collections"].add(str(ref.run))
                    if patch is not None:
                        templates_by_tract_band[key]["patches"].add(patch)

        except Exception as e:
            logging.debug(f"Could not query {dt_name}: {e}")
            continue

    if not templates_by_tract_band:
        formatters.print_warning("No template coadds found")
        return 1

    # Filter by band if requested
    if args.band:
        templates_by_tract_band = {
            k: v for k, v in templates_by_tract_band.items() if k[1] == args.band
        }

        if not templates_by_tract_band:
            formatters.print_warning(f"No templates found for band: {args.band}")
            return 1

    # Build table
    table_data = []
    for (tract, band), info in sorted(templates_by_tract_band.items()):
        n_patches = len(info["patches"])
        n_collections = len(info["collections"])

        table_data.append(
            {
                "Tract": tract,
                "Band": band,
                "Patches": n_patches,
                "Collections": n_collections,
                "Type": info["dataset_type"],
            }
        )

    formatters.output_data(
        table_data,
        format_type=args.format,
        output_file=args.output,
        title="Template Availability",
        column_order=["Tract", "Band", "Patches", "Collections", "Type"],
    )

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Inspect Butler repository contents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Inspection command")

    # Collections command
    parser_collections = subparsers.add_parser(
        "collections",
        help="Show collection hierarchy",
    )
    parser_collections.add_argument(
        "--repo",
        default=os.environ.get("REPO"),
        required=not os.environ.get("REPO"),
        help="Butler repository path (or set $REPO)",
    )
    parser_collections.add_argument(
        "--pattern",
        help="Filter collections by glob pattern",
    )
    parser_collections.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_collections.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    # Datasets command
    parser_datasets = subparsers.add_parser(
        "datasets",
        help="Show dataset inventory",
    )
    parser_datasets.add_argument(
        "--repo",
        default=os.environ.get("REPO"),
        required=not os.environ.get("REPO"),
        help="Butler repository path (or set $REPO)",
    )
    parser_datasets.add_argument(
        "--collection",
        required=True,
        help="Collection to inspect (supports wildcards)",
    )
    parser_datasets.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_datasets.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    # Calibrations command
    parser_calibs = subparsers.add_parser(
        "calibs",
        help="Show calibration coverage",
    )
    parser_calibs.add_argument(
        "--repo",
        default=os.environ.get("REPO"),
        required=not os.environ.get("REPO"),
        help="Butler repository path (or set $REPO)",
    )
    parser_calibs.add_argument(
        "--nights",
        help="Comma-separated list of nights (YYYYMMDD) to check",
    )
    parser_calibs.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_calibs.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    # Templates command
    parser_templates = subparsers.add_parser(
        "templates",
        help="Show template availability",
    )
    parser_templates.add_argument(
        "--repo",
        default=os.environ.get("REPO"),
        required=not os.environ.get("REPO"),
        help="Butler repository path (or set $REPO)",
    )
    parser_templates.add_argument(
        "--band",
        help="Filter by band (e.g., r, i)",
    )
    parser_templates.add_argument(
        "--format",
        choices=["table", "json", "csv", "tsv"],
        default="table",
        help="Output format (default: table)",
    )
    parser_templates.add_argument(
        "--output",
        help="Output file (otherwise print to stdout)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="[%(levelname)s] %(message)s")

    # Dispatch to command handler
    if args.command == "collections":
        return cmd_collections(args)
    elif args.command == "datasets":
        return cmd_datasets(args)
    elif args.command == "calibs":
        return cmd_calibs(args)
    elif args.command == "templates":
        return cmd_templates(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
