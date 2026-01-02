#!/usr/bin/env python3
"""
Count exposures per filter per night for template reference nights.
Reads the template_reference.yaml and queries the Butler.
"""
import argparse
from collections import defaultdict

import yaml
from lsst.daf.butler import Butler


def count_exposures(butler_repo: str, object_name: str, template_yaml: str):
    """Count exposures per filter per night from template YAML."""

    # Load template reference YAML
    with open(template_yaml) as f:
        config = yaml.safe_load(f)

    nights = list(config["nights"].keys())
    nights_int = [
        int(n) for n in nights if isinstance(n, int) or not str(n).startswith("#")
    ]

    # Initialize Butler
    butler = Butler(butler_repo)
    registry = butler.registry

    # Query for raw exposures
    results = defaultdict(lambda: defaultdict(int))

    # Note: day_obs is typically +1 from the calendar night date
    # (because observing night starts at noon)
    for night in nights_int:
        # Try both the night date and next day
        for day_offset in [0, 1]:
            day_obs = night + day_offset
            night_where = f"exposure.observation_type = 'science' AND exposure.day_obs = {day_obs} AND exposure.target_name = '{object_name}'"

            try:
                exposures = registry.queryDimensionRecords(
                    "exposure", where=night_where, instrument="Nickel"
                )

                for exp in exposures:
                    # Get the physical filter (convert to lowercase)
                    filter_name = exp.physical_filter.lower()
                    results[night][filter_name] += 1

            except Exception as e:
                if day_offset == 1:  # Only warn on last attempt
                    print(f"Warning: Error querying night {night}: {e}")
                continue

    # Print results
    print(f"\nExposure counts for {object_name} template nights:\n")
    print(f"{'Night':<12} {'B':>6} {'V':>6} {'R':>6} {'I':>6} {'Total':>8}")
    print("-" * 52)

    grand_total = 0
    filter_totals = {"b": 0, "v": 0, "r": 0, "i": 0}

    for night in sorted(results.keys()):
        b = results[night].get("b", 0)
        v = results[night].get("v", 0)
        r = results[night].get("r", 0)
        i = results[night].get("i", 0)
        total = b + v + r + i
        grand_total += total
        filter_totals["b"] += b
        filter_totals["v"] += v
        filter_totals["r"] += r
        filter_totals["i"] += i

        print(f"{night:<12} {b:>6} {v:>6} {r:>6} {i:>6} {total:>8}")

    print("-" * 52)
    print(
        f"{'TOTAL':<12} {filter_totals['b']:>6} {filter_totals['v']:>6} {filter_totals['r']:>6} {filter_totals['i']:>6} {grand_total:>8}"
    )


def main():
    parser = argparse.ArgumentParser(description="Count template exposures per night")
    parser.add_argument("--repo", required=True, help="Butler repository path")
    parser.add_argument(
        "--object", default="2023ixf", help="Object name (default: 2023ixf)"
    )
    parser.add_argument(
        "--template-yaml",
        default="scripts/config/2023ixf/template_reference.yaml",
        help="Path to template_reference.yaml",
    )

    args = parser.parse_args()
    count_exposures(args.repo, args.object, args.template_yaml)


if __name__ == "__main__":
    main()
