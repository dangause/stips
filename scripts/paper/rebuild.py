#!/usr/bin/env python
"""Rebuild every paper result from raw data, from the checkout this runs in.

Reads ``scripts/paper/targets.yaml``. For each target it writes a run config
(the tracked config with REPO and INSTRUMENT_DIR pointed at this rebuild),
runs ``stips run``, extracts the per-visit products the paper uses, and
records provenance. Supernova campaigns go one night at a time and prune each
night's intermediates afterwards, so disk stays bounded.

Resumable: a night or target with a ``.done.json`` marker is skipped, so an
interrupted rebuild picks up where it stopped. Delete a marker to redo it.

Layout under --out:
    repos/<target>_repo/            Butler repos (pruned for per_night targets)
    configs/<target>/<night>.yaml   the exact configs that were run
    logs/<target>/<night>.log       stips output per step
    products/<target>/              CSVs and plots the paper reads
    products/PROVENANCE.json        code version, stack, host, time

Usage:
    .venv/bin/python scripts/paper/rebuild.py --out /data/paper_v2.1.1
    .venv/bin/python scripts/paper/rebuild.py --out ... --targets 2023ixf landolt
    .venv/bin/python scripts/paper/rebuild.py --out ... --dry-run
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STIPS = ROOT / ".venv" / "bin" / "stips"
WITH_STACK = ROOT / "scripts" / "with-stack.sh"
PRUNE = ROOT / "scripts" / "utilities" / "prune_night.py"
EXPORT = ROOT / "scripts" / "paper" / "export_forced_phot.py"
DEFAULT_PREFIX = "Nickel"  # targets.yaml `prefix:` overrides (CTIO1m)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class Rebuild:
    def __init__(self, out: Path, dry_run: bool):
        self.out = out
        self.dry = dry_run

    # -- plumbing ----------------------------------------------------------
    def sh(self, cmd: list[str], log: Path) -> int:
        print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
        if self.dry:
            return 0
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as fh:
            fh.write(f"\n### {now()} {' '.join(str(c) for c in cmd)}\n")
            fh.flush()
            return subprocess.run(
                [str(c) for c in cmd], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT
            ).returncode

    def stack(self, cfg: dict, args: list, log: Path) -> int:
        return self.sh(
            [WITH_STACK, "-S", cfg["env"]["STACK_DIR"], "--", "python", *args], log
        )

    def target_config(self, name: str, spec: dict) -> dict:
        cfg = yaml.safe_load((ROOT / spec["config"]).read_text())
        if "INSTRUMENT_PACKAGE" in cfg.get("env", {}):
            raise SystemExit(f"{spec['config']}: stale INSTRUMENT_PACKAGE")
        instrument = Path(cfg["env"]["INSTRUMENT_DIR"]).name
        cfg = deep_merge(cfg, spec.get("overrides", {}))
        cfg["env"]["REPO"] = str(self.out / "repos" / f"{name}_repo")
        cfg["env"]["INSTRUMENT_DIR"] = str(ROOT / "instruments" / instrument)
        return cfg

    def write_config(self, cfg: dict, name: str, label: str) -> Path:
        path = self.out / "configs" / name / f"{label}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        return path

    @staticmethod
    def marker(path: Path) -> dict | None:
        return json.loads(path.read_text()) if path.exists() else None

    def mark(self, path: Path, record: dict) -> None:
        if self.dry:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2))

    # -- extraction --------------------------------------------------------
    def extract(self, name, spec, cfg_path, cfg, products, log, night=None):
        status = {}
        extract = spec.get("extract", [])
        if "calib_metrics" in extract:
            out = products / "calib_metrics" / f"{night or 'all'}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = [STIPS, "-c", cfg_path, "calib-metrics", "-o", out]
            if night:
                cmd += [
                    "--night",
                    night,
                    "--collection",
                    f"{spec.get('prefix', DEFAULT_PREFIX)}/runs/{night}/processCcd/*",
                ]
            status["calib_metrics"] = self.sh(cmd, log)
        if "landolt" in extract and not night:
            catalog = ROOT / "scripts/config/landolt_validation/landolt_catalog.csv"
            out = products / "landolt_validation.csv"
            status["landolt"] = self.sh(
                [
                    STIPS,
                    "-c",
                    cfg_path,
                    "landolt-validate",
                    "--catalog",
                    catalog,
                    "-o",
                    out,
                ],
                log,
            )
        return status

    def export_forced_phot(self, cfg, products, log) -> int:
        products.mkdir(parents=True, exist_ok=True)
        return self.stack(
            cfg, [EXPORT, cfg["env"]["REPO"], products / "forced_phot_all.csv"], log
        )

    def lightcurve(self, cfg, cfg_path, products, log) -> int:
        lc = cfg.get("lightcurve") or {}
        if not lc or "ra" not in cfg:
            return 0
        cmd = [
            STIPS, "-c", cfg_path, "lightcurve",
            "--ra", cfg["ra"], "--dec", cfg["dec"],
            "--collections", f"{DEFAULT_PREFIX}/runs/*/forcedPhotRaDec/*",
            "--dataset-type", lc.get("dataset_type", "forced_phot_diffim_radec"),
            "--min-snr", lc.get("min_snr", 3.0),
            "--y-axis", lc.get("y_axis", "apparent_mag"),
            "--x-axis", lc.get("x_axis", "mjd"),
            "--name", cfg.get("object", ""),
            "-o", products / "lightcurve.csv",
        ]  # fmt: skip
        for key, flag in (
            ("explosion_mjd", "--explosion-mjd"),
            ("distance_modulus", "--distance-modulus"),
            ("max_mag_err", "--max-mag-err"),
        ):
            if lc.get(key) is not None:
                cmd += [flag, lc[key]]
        return self.sh(cmd, log)

    @staticmethod
    def combine_metrics(products: Path) -> None:
        parts = sorted((products / "calib_metrics").glob("*.csv"))
        per_night = [p for p in parts if p.name != "all.csv"]
        # per_night targets write one CSV per night; whole targets write all.csv.
        parts = per_night or parts
        rows, fields = [], []
        for part in parts:
            with open(part, newline="") as fh:
                reader = csv.DictReader(fh)
                fields += [f for f in reader.fieldnames or [] if f not in fields]
                rows += list(reader)
        if rows:
            with open(products / "calib_metrics.csv", "w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

    # -- modes -------------------------------------------------------------
    def per_night(self, name, spec, cfg):
        products = self.out / "products" / name
        for night in [str(n) for n in cfg["science"]["nights"]]:
            done = products / "nights" / f"{night}.done.json"
            if self.marker(done):
                print(f"[{name}] {night}: done, skipping")
                continue
            print(f"[{name}] {night}: start {now()}", flush=True)
            ncfg = copy.deepcopy(cfg)
            ncfg["science"]["nights"] = [int(night)]
            ncfg.setdefault("lightcurve", {})["enabled"] = False
            path = self.write_config(ncfg, name, night)
            log = self.out / "logs" / name / f"{night}.log"
            rc = self.sh([STIPS, "-c", path, "run"], log)
            status = {"run": rc, **self.extract(name, spec, path, ncfg, products,
                                                log, night)}  # fmt: skip
            if night in {str(n) for n in spec.get("keep_nights", [])}:
                status["prune"] = "kept for figures"
            else:
                status["prune"] = self.stack(
                    cfg, [PRUNE, cfg["env"]["REPO"], night], log
                )
            self.mark(done, {"night": night, "finished": now(), "status": status})
        full = self.write_config(cfg, name, "all_nights")
        log = self.out / "logs" / name / "final.log"
        self.export_forced_phot(cfg, products, log)
        self.lightcurve(cfg, full, products, log)
        self.combine_metrics(products)

    def whole(self, name, spec, cfg):
        products = self.out / "products" / name
        done = products / "target.done.json"
        if self.marker(done):
            print(f"[{name}] done, skipping")
            return
        print(f"[{name}] start {now()}", flush=True)
        path = self.write_config(cfg, name, "all_nights")
        log = self.out / "logs" / name / "run.log"
        status = {"run": self.sh([STIPS, "-c", path, "run"], log)}
        status.update(self.extract(name, spec, path, cfg, products, log))
        if "forced_phot" in spec.get("extract", []):
            status["forced_phot"] = self.export_forced_phot(cfg, products, log)
        lc_dir = Path(cfg["env"]["REPO"]) / "lightcurves"
        if lc_dir.is_dir() and not self.dry:
            shutil.copytree(lc_dir, products / "lightcurves", dirs_exist_ok=True)
        self.combine_metrics(products)
        self.mark(done, {"finished": now(), "status": status})

    # -- provenance --------------------------------------------------------
    def provenance(self, manifest: dict) -> None:
        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True
            ).stdout.strip()

        record = {
            "written": now(),
            "stips_describe": git("describe", "--tags", "--always", "--dirty"),
            "stips_commit": git("rev-parse", "HEAD"),
            "host": platform.node(),
            "python": sys.version.split()[0],
            "manifest": manifest,
        }
        path = self.out / "products" / "PROVENANCE.json"
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            history = json.loads(path.read_text()) if path.exists() else []
            history.append(record)
            path.write_text(json.dumps(history, indent=2))
        if record["stips_describe"].endswith("-dirty"):
            print("WARNING: rebuilding from a dirty checkout", file=sys.stderr)


def assemble(products: Path) -> None:
    """Write the file names the figure scripts read (scripts/analysis/paper_data.py).

    calib_metrics/combined.csv      every target's metrics with a `target` column
    landolt_validation_4nights.csv  the Landolt target's validation table
    lightcurve_<target>.csv         each target's extracted lightcurve
    """
    rows, fields = [], ["target"]
    for target_dir in sorted(p for p in products.iterdir() if p.is_dir()):
        metrics = target_dir / "calib_metrics.csv"
        if metrics.exists():
            with open(metrics, newline="") as fh:
                reader = csv.DictReader(fh)
                fields += [f for f in reader.fieldnames or [] if f not in fields]
                rows += [{"target": target_dir.name, **r} for r in reader]
        lightcurve = target_dir / "lightcurve.csv"
        if lightcurve.exists():
            shutil.copy(lightcurve, products / f"lightcurve_{target_dir.name}.csv")
    if rows:
        (products / "calib_metrics").mkdir(exist_ok=True)
        with open(products / "calib_metrics" / "combined.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    landolt = products / "landolt" / "landolt_validation.csv"
    if landolt.exists():
        shutil.copy(landolt, products / "landolt_validation_4nights.csv")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--targets", nargs="*", help="subset of targets.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = yaml.safe_load((ROOT / "scripts/paper/targets.yaml").read_text())
    names = args.targets or list(manifest["targets"])
    unknown = set(names) - set(manifest["targets"])
    if unknown:
        parser.error(f"unknown targets: {sorted(unknown)}")

    rb = Rebuild(args.out.resolve(), args.dry_run)
    rb.provenance({n: manifest["targets"][n] for n in names})
    for name in names:
        spec = manifest["targets"][name]
        cfg = rb.target_config(name, spec)
        getattr(rb, spec["mode"])(name, spec, cfg)
    if not args.dry_run:
        assemble(rb.out / "products")
    print(f"done {now()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
