#!/usr/bin/env python
"""Export every forced-photometry row in a repo to one CSV (runs in the stack).

Unlike ``stips lightcurve`` this applies no S/N or error cut, so
non-detections stay in the table and upper limits can be computed from it.
Each row carries its visit's band, filter, mid-exposure MJD and exposure time,
plus the dataset type and RUN collection it came from.

Usage (stack python): export_forced_phot.py REPO OUTPUT_CSV [COLLECTION_GLOB]
"""

from __future__ import annotations

import csv
import sys

from lsst.daf.butler import Butler

DATASET_TYPES = ("forced_phot_diffim_radec", "forced_phot_radec")


def main() -> int:
    repo, output = sys.argv[1], sys.argv[2]
    glob = sys.argv[3] if len(sys.argv) > 3 else "*/runs/*/forcedPhotRaDec/*"
    butler = Butler.from_config(repo)
    registry_types = {dt.name for dt in butler.registry.queryDatasetTypes()}

    runs = [
        c
        for c in butler.collections.query(glob)
        if butler.collections.get_info(c).type.name == "RUN"
    ]
    rows: list[dict] = []
    for dataset_type in DATASET_TYPES:
        if dataset_type not in registry_types:
            continue
        for run in sorted(runs):
            for ref in butler.query_datasets(
                dataset_type, collections=run, explain=False
            ):
                visit = butler.query_dimension_records(
                    "visit", data_id=ref.dataId, explain=False
                )[0]
                span = visit.timespan
                mjd_mid = (span.begin.mjd + span.end.mjd) / 2 if span else None
                table = butler.get(ref)
                df = table.to_pandas() if hasattr(table, "to_pandas") else table
                for rec in df.to_dict("records"):
                    rows.append(
                        {
                            "dataset_type": dataset_type,
                            "run": run,
                            "visit": ref.dataId["visit"],
                            "band": ref.dataId["band"],
                            "physical_filter": visit.physical_filter,
                            "day_obs": visit.day_obs,
                            "mjd_mid": mjd_mid,
                            "exposure_time": visit.exposure_time,
                            "target_name": visit.target_name,
                            **rec,
                        }
                    )

    fields: list[str] = []
    for row in rows:
        fields += [k for k in row if k not in fields]
    with open(output, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[export] {len(rows)} rows from {len(runs)} runs -> {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
