"""Analysis data helpers for the dashboard."""

from __future__ import annotations

import csv
from pathlib import Path


def find_lightcurve_files(logs_dir: Path, run_id: str) -> dict:
    """Find lightcurve output files referenced in summary.txt.

    Returns dict with keys: csv_path, png_path, repo_path, found.
    """
    result: dict = {
        "csv_path": None,
        "png_path": None,
        "repo_path": None,
        "found": False,
    }

    summary = logs_dir / run_id / "summary.txt"
    if summary.exists():
        text = summary.read_text()
        for line in text.splitlines():
            if line.startswith("Lightcurve:"):
                csv_path = line.split(":", 1)[1].strip()
                if csv_path and csv_path != "None":
                    p = Path(csv_path)
                    result["csv_path"] = str(p) if p.exists() else None
                    png = p.parent / f"{p.stem}.png"
                    result["png_path"] = str(png) if png.exists() else None
                    result["repo_path"] = str(p.parent)
                    result["found"] = True
            if line.startswith("Repository:"):
                result["repo_path"] = line.split(":", 1)[1].strip()

    # Also check repo-based lightcurves dir if not found from summary
    if not result["found"]:
        run_info = logs_dir / run_id / "run_info.txt"
        if run_info.exists():
            for line in run_info.read_text().splitlines():
                if line.startswith("Repository:"):
                    repo = Path(line.split(":", 1)[1].strip())
                    lc_dir = repo / "lightcurves"
                    if lc_dir.is_dir():
                        result["repo_path"] = str(lc_dir)
                        csvs = sorted(
                            lc_dir.glob("*.csv"),
                            key=lambda f: f.stat().st_mtime,
                            reverse=True,
                        )
                        if csvs:
                            result["csv_path"] = str(csvs[0])
                            png = csvs[0].parent / f"{csvs[0].stem}.png"
                            result["png_path"] = str(png) if png.exists() else None
                            result["found"] = True

    return result


def parse_lightcurve_csv(csv_path: str) -> dict:
    """Parse a lightcurve CSV file into JSON-serializable format for Plotly.

    Returns dict with keys: columns, data (list of rows), bands (unique band values).
    """
    path = Path(csv_path)
    if not path.exists():
        return {"columns": [], "data": [], "bands": []}

    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        for row in reader:
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)

    bands = sorted(set(r.get("band", "") for r in rows if r.get("band")))

    return {"columns": columns, "data": rows, "bands": bands}


def find_output_images(logs_dir: Path, run_id: str) -> list[dict]:
    """Find all output images (PNGs) associated with a run."""
    lc = find_lightcurve_files(logs_dir, run_id)
    images: list[dict] = []

    if lc.get("png_path"):
        images.append(
            {
                "name": Path(lc["png_path"]).name,
                "path": lc["png_path"],
                "type": "lightcurve",
            }
        )

    if lc.get("repo_path"):
        lc_dir = Path(lc["repo_path"])
        if lc_dir.is_dir():
            for png in sorted(lc_dir.glob("*.png")):
                if str(png) != lc.get("png_path"):
                    images.append(
                        {
                            "name": png.name,
                            "path": str(png),
                            "type": "plot",
                        }
                    )

    return images
