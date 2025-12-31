#!/usr/bin/env python3
"""
Generate reference YAML files mapping observing nights → day_obs → filter → visits

This script queries the Butler SQLite registry to build reference files
that map observing night labels (used in collection paths) to UT day_obs
values (used in FITS headers and Butler queries).
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def day_obs_to_obs_night(day_obs):
    """Convert UT day_obs to local observing night (subtract 1 day)."""
    dt = datetime.strptime(str(day_obs), "%Y%m%d")
    obs_night_dt = dt - timedelta(days=1)
    return int(obs_night_dt.strftime("%Y%m%d"))


def query_visits(db_path, object_name):
    """Query Butler registry for all visits grouped by day_obs and filter."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT day_obs, physical_filter, GROUP_CONCAT(id, ', ') as visits
        FROM exposure
        WHERE instrument = 'Nickel' AND target_name = ?
        GROUP BY day_obs, physical_filter
        ORDER BY day_obs, physical_filter
    """

    cursor.execute(query, (object_name,))
    results = cursor.fetchall()
    conn.close()

    # Organize by obs_night → day_obs → filter → visits
    nights = {}
    for day_obs, filter_name, visit_str in results:
        obs_night = day_obs_to_obs_night(day_obs)

        if obs_night not in nights:
            nights[obs_night] = {"day_obs": day_obs, "filters": {}}

        # Convert filter names (V, R, B, I) to lowercase (v, r, b, i)
        filter_lower = filter_name.lower()

        # Parse visit IDs
        visits = [int(v.strip()) for v in visit_str.split(",")]
        nights[obs_night]["filters"][filter_lower] = visits

    return nights


def write_yaml(nights, output_path, object_name, description):
    """Write nights data to YAML file."""
    with open(output_path, "w") as f:
        f.write(f"# {description}\n")
        f.write("# Schema: observing_night → day_obs → filter → visit IDs\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write("#\n")
        f.write(
            "# Observing night = local date when observations BEGIN (used for collection paths like Nickel/raw/YYYYMMDD)\n"
        )
        f.write("# day_obs = UT date in FITS headers (used for Butler WHERE clauses)\n")
        f.write("# For California (UTC-8), day_obs is typically obs_night + 1 day\n")
        f.write("\n")
        f.write(f'object: "{object_name}"\n')
        f.write("\n")
        f.write("nights:\n")

        for obs_night in sorted(nights.keys()):
            night_data = nights[obs_night]
            f.write(f"  {obs_night}:\n")
            f.write(f"    day_obs: {night_data['day_obs']}\n")
            f.write("    filters:\n")

            # Write filters in canonical order: v, r, b, i
            for filter_name in ["v", "r", "b", "i"]:
                if filter_name in night_data["filters"]:
                    visits = night_data["filters"][filter_name]
                    visits_str = ", ".join(str(v) for v in visits)
                    f.write(f"      {filter_name}: [{visits_str}]\n")
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate reference YAML files from Butler registry"
    )
    parser.add_argument("repo", help="Butler repository path")
    parser.add_argument("object", help="Target object name")
    parser.add_argument("--output", required=True, help="Output YAML file path")
    parser.add_argument(
        "--description", default="Nights reference", help="Description for YAML header"
    )
    parser.add_argument(
        "--start-date", type=int, help="Start date filter (day_obs, YYYYMMDD)"
    )
    parser.add_argument(
        "--end-date", type=int, help="End date filter (day_obs, YYYYMMDD)"
    )

    args = parser.parse_args()

    # Find Butler registry database
    repo_path = Path(args.repo)
    db_path = repo_path / "gen3.sqlite3"

    if not db_path.exists():
        print(f"ERROR: Butler registry not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Querying Butler registry: {db_path}")
    print(f"Target object: {args.object}")

    # Query all visits
    all_nights = query_visits(str(db_path), args.object)

    # Apply date filtering if specified
    if args.start_date or args.end_date:
        filtered_nights = {}
        for obs_night, night_data in all_nights.items():
            day_obs = night_data["day_obs"]
            if args.start_date and day_obs < args.start_date:
                continue
            if args.end_date and day_obs > args.end_date:
                continue
            filtered_nights[obs_night] = night_data
        nights = filtered_nights
        print(f"Date filter: {args.start_date or 'any'} to {args.end_date or 'any'}")
        print(f"Filtered: {len(nights)}/{len(all_nights)} nights")
    else:
        nights = all_nights

    if not nights:
        print("ERROR: No nights found matching criteria", file=sys.stderr)
        sys.exit(1)

    print(f"Writing {len(nights)} nights to {args.output}")
    write_yaml(nights, args.output, args.object, args.description)
    print("Done!")


if __name__ == "__main__":
    main()
