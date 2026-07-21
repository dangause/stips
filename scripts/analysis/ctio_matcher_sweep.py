"""CTIO Y4KCam calibrateImage matcher/selection sweep.

Renders candidate calibrateImage configs over a knob grid, runs each on a
fixed NGC2298 night via `stips science --calibrate-config`, scores match-rate
and astrometric precision from calib-metrics, and prints a ranked table.
Used to fit instruments/ctio1m/configs/calibrateImage/ctio_dense.py empirically
(Y4KCam is 0.29"/pix, ~20' FOV, 4064x4064, 4 amps; do NOT reuse Nickel values).
"""
from __future__ import annotations

import argparse
import csv
import itertools
import statistics
import subprocess
from pathlib import Path

# Neutral measurement-schema block every candidate MUST keep (else downstream
# stage-1 fails on the missing aperture-flux ladder).
_SCHEMA_BLOCK = '''\
config.star_measurement.plugins.names |= [
    "base_CircularApertureFlux", "base_LocalBackground", "base_PsfFlux",
    "base_SdssCentroid", "base_SdssShape", "base_PixelFlags", "base_Variance",
    "base_Blendedness", "base_Jacobian",
    "ext_shapeHSM_HsmPsfMomentsDebiased", "ext_shapeHSM_HsmShapeRegauss",
]
config.star_measurement.plugins["base_CircularApertureFlux"].radii = [
    3.0, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0,
]
config.star_measurement.plugins["base_CircularApertureFlux"].maxSincRadius = 12.0
config.star_measurement.plugins.names |= ["base_CompensatedTophatFlux"]
config.star_measurement.plugins["base_CompensatedTophatFlux"].apertures = [12, 17]
try:
    config.star_measurement.slots.apFlux = "base_CircularApertureFlux_17_0"
except Exception:
    pass
'''


def build_config_grid(base: dict, axes: dict[str, list]) -> list[dict]:
    keys = list(axes)
    grid = []
    for combo in itertools.product(*(axes[k] for k in keys)):
        merged = dict(base)
        merged.update(dict(zip(keys, combo)))
        grid.append(merged)
    return grid


def render_config(knobs: dict, out_path: Path) -> Path:
    k = knobs
    body = f'''# ruff: noqa: F821
# CTIO Y4KCam calibrateImage sweep candidate (auto-generated).
config.astrometry.matcher.maxOffsetPix = {k["maxOffsetPix"]}
config.astrometry.matcher.maxRotationDeg = {k["maxRotationDeg"]}
config.astrometry.matcher.minMatchedPairs = {k["minMatchedPairs"]}
config.astrometry.matcher.minFracMatchedPairs = {k["minFracMatchedPairs"]}
config.astrometry.matcher.numBrightStars = {k["numBrightStars"]}
config.astrometry.matcher.maxRefObjects = {k["maxRefObjects"]}
config.astrometry.matcher.numPatternConsensus = {k["numPatternConsensus"]}
config.astrometry.referenceSelector.doMagLimit = True
config.astrometry.referenceSelector.magLimit.minimum = {k["magLimitMin"]}
config.astrometry.referenceSelector.magLimit.maximum = {k["magLimitMax"]}
config.astrometry_ref_loader.pixelMargin = {k["pixelMargin"]}
config.psf_detection.thresholdType = "stdev"
config.psf_detection.thresholdValue = {k["psfThreshold"]}
config.psf_measure_psf.psfDeterminer["psfex"].spatialOrder = {k["psfSpatialOrder"]}

{_SCHEMA_BLOCK}'''
    out_path.write_text(body)
    return out_path


def score_csv(csv_path: Path, attempted: int) -> dict:
    with open(csv_path, newline="") as _fh:
        rows = list(csv.DictReader(_fh))
    vals = []
    for r in rows:
        v = r.get("astromOffsetMean")
        if v not in (None, "", "nan", "NaN"):
            f = float(v)
            if f > 1e-6:
                vals.append(f)
    n_pass = len(vals)
    return {
        "n_pass": n_pass,
        "match_rate": (n_pass / attempted) if attempted else 0.0,
        "mean_sep": statistics.mean(vals) if vals else float("nan"),
        "max_sep": max(vals) if vals else float("nan"),
    }


def format_table(results: list[dict]) -> str:
    ranked = sorted(results, key=lambda r: (-r["match_rate"], r["mean_sep"]))
    lines = [f"{'LABEL':<24} {'MATCH_RATE':>10} {'MEAN_SEP\"':>10} {'MAX_SEP\"':>9}"]
    for r in ranked:
        lines.append(
            f"{r['label']:<24} {r['match_rate']:>10.3f} {r['mean_sep']:>10.3f} {r['max_sep']:>9.3f}"
        )
    return "\n".join(lines)


def _run_candidate(cfg_yaml: str, night: str, ra: float, dec: float,
                   cfg_path: Path, metrics_dir: Path, label: str) -> dict:
    """Run one candidate via stips science + calib-metrics; return a scored row."""
    subprocess.run(
        [".venv/bin/stips", "-c", cfg_yaml, "clean", "--night", night, "--step", "science", "-y"],
        check=False,
    )
    subprocess.run(
        [".venv/bin/stips", "-c", cfg_yaml, "science", night, "--object", "NGC2298",
         "--ra", str(ra), "--dec", str(dec), "--skip-coadds", "--calibrate-config", str(cfg_path),
         "-j", "4"],
        check=False,
    )
    out_csv = metrics_dir / f"{label}.csv"
    attempted = _count_attempted(cfg_yaml, night)
    subprocess.run(
        [".venv/bin/stips", "-c", cfg_yaml, "calib-metrics",
         "--collection", "CTIO1m/runs/*/processCcd/*", "--night", night, "-o", str(out_csv)],
        check=False,
    )
    s = score_csv(out_csv, attempted)
    s["label"] = label
    return s


def _count_attempted(cfg_yaml: str, night: str) -> int:
    """Number of science visits attempted this night (raw exposures ingested)."""
    # Best-effort: count ingested raws for the night from the repo. Falls back to
    # a caller-supplied --attempted when the query is unavailable.
    raise NotImplementedError("pass --attempted explicitly; wired at execution")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="NGC2298 pipeline yaml")
    ap.add_argument("--night", required=True)
    ap.add_argument("--ra", type=float, default=102.246542)
    ap.add_argument("--dec", type=float, default=-36.005333)
    ap.add_argument("--attempted", type=int, required=True,
                    help="visits attempted this night (for match-rate denominator)")
    ap.add_argument("--workdir", type=Path, default=Path("analysis/sweep"))
    args = ap.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)

    # CTIO-scaled starting base + sweep axes (edit per iteration).
    base = dict(maxOffsetPix=800, maxRotationDeg=1.0, minMatchedPairs=15,
                minFracMatchedPairs=0.05, numBrightStars=300, maxRefObjects=10000,
                numPatternConsensus=3, magLimitMin=11.0, magLimitMax=18.0,
                pixelMargin=400, psfThreshold=5.0, psfSpatialOrder=2)
    axes = {"maxOffsetPix": [600, 800, 1000],
            "minFracMatchedPairs": [0.03, 0.05],
            "magLimitMax": [17.0, 18.0, 19.0]}

    results = []
    for i, knobs in enumerate(build_config_grid(base, axes)):
        label = f"cand{i:02d}"
        cfg_path = render_config(knobs, args.workdir / f"{label}.py")
        results.append(
            _run_candidate(args.config, args.night, args.ra, args.dec,
                           cfg_path, args.workdir, label)
        )
    print(format_table(results))


if __name__ == "__main__":
    main()
