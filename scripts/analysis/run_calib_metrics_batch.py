#!/usr/bin/env python
"""Batch runner: extract calibration metrics across 5 repos, combine into one CSV."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

# Repo root (relative to this script)
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "analysis" / "calib_metrics"

TARGETS = [
    {
        "name": "2023ixf",
        "config": "scripts/config/2023ixf/pipeline_ps1_template.yaml",
    },
    {
        "name": "2020wnt",
        "config": "scripts/config/2020wnt/pipeline_ps1_template.yaml",
    },
    {
        "name": "hd189733",
        "config": "scripts/config/hd189733/pipeline_transit.yaml",
    },
    {
        "name": "ac_and",
        "config": "scripts/config/ac_and/pipeline.yaml",
    },
    {
        "name": "extended_objects",
        "config": "scripts/config/extended_objects/pipeline_calibs_science.yaml",
    },
]


def run_one(target: dict) -> Path | None:
    """Run nickel calib-metrics for a single target. Returns CSV path or None."""
    name = target["name"]
    config = REPO_ROOT / target["config"]
    output = OUTPUT_DIR / f"{name}.csv"

    if not config.exists():
        print(f"[skip] config not found: {config}", file=sys.stderr)
        return None

    nickel = str(Path(sys.executable).parent / "nickel")
    cmd = [nickel, "calib-metrics", str(config), "-o", str(output)]
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[run] {name}: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[FAIL] {name} returned {result.returncode}", file=sys.stderr)
        return None

    if output.exists():
        print(f"[ok] {name} -> {output}", file=sys.stderr)
        return output
    return None


def combine(csv_paths: dict[str, Path]) -> Path:
    """Combine per-target CSVs into one with a 'target' column."""
    combined = OUTPUT_DIR / "combined.csv"
    all_rows = []
    fieldnames = None

    for target_name, csv_path in sorted(csv_paths.items()):
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            if fieldnames is None:
                fieldnames = ["target"] + list(reader.fieldnames or [])
            for row in reader:
                row["target"] = target_name
                all_rows.append(row)

    if not all_rows or not fieldnames:
        print("[error] no rows to combine", file=sys.stderr)
        return combined

    with open(combined, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n[ok] combined {len(all_rows)} rows -> {combined}", file=sys.stderr)
    return combined


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}
    for target in TARGETS:
        path = run_one(target)
        if path:
            results[target["name"]] = path

    if results:
        combine(results)
        print(f"\n{'='*60}", file=sys.stderr)
        print(
            f"[done] {len(results)}/{len(TARGETS)} targets succeeded", file=sys.stderr
        )
    else:
        print("[error] all targets failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
