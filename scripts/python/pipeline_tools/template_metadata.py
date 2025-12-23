#!/opt/anaconda3/envs/lsst-scipipe-12.0.0/bin/python
"""
template_metadata.py - Track and query template date ranges

This module helps manage template metadata, particularly date ranges used
in template construction. Critical for avoiding contamination from transients.

Usage:
    # Record template metadata when building
    python template_metadata.py record \
        --repo $REPO \
        --collection templates/deep/r \
        --start 20210101 \
        --end 20210131

    # Query templates excluding certain date ranges
    python template_metadata.py query \
        --repo $REPO \
        --exclude-start 20210219 \
        --exclude-end 20210228

    # List all template metadata
    python template_metadata.py list --repo $REPO
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class TemplateMetadata:
    """Manager for template metadata including date ranges."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.metadata_file = self.repo_path / "template_metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        """Load existing metadata or create new."""
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                return json.load(f)
        return {"templates": {}}

    def _save_metadata(self):
        """Save metadata to file."""
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2)

    def record_template(
        self,
        collection: str,
        start_date: str,
        end_date: str,
        tract: Optional[str] = None,
        band: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """Record metadata for a template collection.

        Parameters
        ----------
        collection : str
            Template collection name (e.g., "templates/deep/r")
        start_date : str
            Earliest observation date (YYYYMMDD)
        end_date : str
            Latest observation date (YYYYMMDD)
        tract : str, optional
            Sky tract ID
        band : str, optional
            Filter band
        description : str, optional
            Human-readable description
        """
        # Validate dates
        try:
            start = datetime.strptime(start_date, "%Y%m%d")
            end = datetime.strptime(end_date, "%Y%m%d")
            if start > end:
                raise ValueError("start_date must be <= end_date")
        except ValueError as e:
            raise ValueError(f"Invalid date format or range: {e}")

        # Store metadata
        self.metadata["templates"][collection] = {
            "start_date": start_date,
            "end_date": end_date,
            "tract": tract,
            "band": band,
            "description": description or f"Template from {start_date} to {end_date}",
            "created": datetime.now().isoformat(),
        }

        self._save_metadata()
        print(f"Recorded metadata for {collection}")
        print(f"  Date range: {start_date} - {end_date}")
        if tract:
            print(f"  Tract: {tract}")
        if band:
            print(f"  Band: {band}")

    def query_templates(
        self,
        exclude_start: Optional[str] = None,
        exclude_end: Optional[str] = None,
        required_band: Optional[str] = None,
        required_tract: Optional[str] = None,
    ) -> list[str]:
        """Query templates that don't overlap with exclusion date range.

        Parameters
        ----------
        exclude_start : str, optional
            Start of date range to exclude (YYYYMMDD)
        exclude_end : str, optional
            End of date range to exclude (YYYYMMDD)
        required_band : str, optional
            Only return templates in this band
        required_tract : str, optional
            Only return templates for this tract

        Returns
        -------
        list[str]
            List of template collection names that match criteria
        """
        if exclude_start and exclude_end:
            try:
                excl_start = datetime.strptime(exclude_start, "%Y%m%d")
                excl_end = datetime.strptime(exclude_end, "%Y%m%d")
            except ValueError as e:
                raise ValueError(f"Invalid exclusion date format: {e}")
        else:
            excl_start = excl_end = None

        matching = []
        for collection, meta in self.metadata["templates"].items():
            # Check band filter
            if required_band and meta.get("band") != required_band:
                continue

            # Check tract filter
            if required_tract and meta.get("tract") != required_tract:
                continue

            # Check date overlap
            if excl_start and excl_end:
                tmpl_start = datetime.strptime(meta["start_date"], "%Y%m%d")
                tmpl_end = datetime.strptime(meta["end_date"], "%Y%m%d")

                # Check if template overlaps with exclusion range
                # No overlap if: template ends before exclusion starts OR template starts after exclusion ends
                no_overlap = tmpl_end < excl_start or tmpl_start > excl_end

                if not no_overlap:
                    continue  # Skip this template (it overlaps with exclusion)

            matching.append(collection)

        return matching

    def list_templates(self, verbose: bool = False):
        """Print all template metadata.

        Parameters
        ----------
        verbose : bool
            Include all metadata fields
        """
        if not self.metadata["templates"]:
            print("No template metadata found.")
            print(f"Metadata file: {self.metadata_file}")
            return

        print(f"\nTemplate Metadata ({len(self.metadata['templates'])} templates)")
        print(f"File: {self.metadata_file}")
        print("=" * 80)

        for collection, meta in sorted(self.metadata["templates"].items()):
            print(f"\n{collection}")
            print(f"  Date range: {meta['start_date']} - {meta['end_date']}")

            if meta.get("band"):
                print(f"  Band: {meta['band']}")
            if meta.get("tract"):
                print(f"  Tract: {meta['tract']}")
            if meta.get("description"):
                print(f"  Description: {meta['description']}")

            if verbose and meta.get("created"):
                print(f"  Created: {meta['created']}")

        print()


def main():
    parser = argparse.ArgumentParser(
        description="Manage template metadata for DIA processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Record command
    record_parser = subparsers.add_parser(
        "record", help="Record metadata for a template collection"
    )
    record_parser.add_argument("--repo", required=True, help="Butler repository path")
    record_parser.add_argument(
        "--collection", required=True, help="Template collection name"
    )
    record_parser.add_argument("--start", required=True, help="Start date (YYYYMMDD)")
    record_parser.add_argument("--end", required=True, help="End date (YYYYMMDD)")
    record_parser.add_argument("--tract", help="Sky tract ID")
    record_parser.add_argument("--band", help="Filter band")
    record_parser.add_argument("--description", help="Description of template")

    # Query command
    query_parser = subparsers.add_parser(
        "query", help="Query templates with date filtering"
    )
    query_parser.add_argument("--repo", required=True, help="Butler repository path")
    query_parser.add_argument(
        "--exclude-start",
        help="Exclude templates overlapping this start date (YYYYMMDD)",
    )
    query_parser.add_argument(
        "--exclude-end", help="Exclude templates overlapping this end date (YYYYMMDD)"
    )
    query_parser.add_argument("--band", help="Filter to specific band")
    query_parser.add_argument("--tract", help="Filter to specific tract")

    # List command
    list_parser = subparsers.add_parser("list", help="List all template metadata")
    list_parser.add_argument("--repo", required=True, help="Butler repository path")
    list_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all metadata"
    )

    args = parser.parse_args()

    # Initialize manager
    metadata_mgr = TemplateMetadata(args.repo)

    # Execute command
    if args.command == "record":
        metadata_mgr.record_template(
            collection=args.collection,
            start_date=args.start,
            end_date=args.end,
            tract=args.tract,
            band=args.band,
            description=args.description,
        )

    elif args.command == "query":
        if args.exclude_start and not args.exclude_end:
            print("ERROR: --exclude-start requires --exclude-end", file=sys.stderr)
            sys.exit(1)
        if args.exclude_end and not args.exclude_start:
            print("ERROR: --exclude-end requires --exclude-start", file=sys.stderr)
            sys.exit(1)

        matching = metadata_mgr.query_templates(
            exclude_start=args.exclude_start,
            exclude_end=args.exclude_end,
            required_band=args.band,
            required_tract=args.tract,
        )

        if not matching:
            print("No templates match the criteria")
            sys.exit(0)

        print(f"\nMatching templates ({len(matching)}):")
        for collection in matching:
            meta = metadata_mgr.metadata["templates"][collection]
            print(f"  {collection}")
            print(f"    Date range: {meta['start_date']} - {meta['end_date']}")

    elif args.command == "list":
        metadata_mgr.list_templates(verbose=args.verbose)


if __name__ == "__main__":
    main()
