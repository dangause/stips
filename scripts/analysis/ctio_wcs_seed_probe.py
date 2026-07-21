"""CTIO Y4KCam initial-WCS seed alignment probe (rotation/scale offset finder).

WHY THIS EXISTS (physical reasoning — do not delete):
NGC2298 (2006, dense southern globular) astrometry fails 0/45 with a UNIVERSAL
~8-9" mean residual (16-22" max) that is INVARIANT to every calibrateImage
lever (matcher tolerances, maxRotationDeg 1->5, source S/N, maxRefObjects,
refcat). matchPessimisticB does not fit plate scale and caps its rotation search
at +/-6 deg, so a wrong *seed* WCS (wrong plate scale or wrong boresight rotation
baked at ingest) cannot be recovered downstream by any config knob. This probe
measures that seed defect ANALYTICALLY, outside the matcher: it projects detected
bright-source pixel centroids through the ingested (seed) WCS to sky, then
grid-searches the (rotation, scale) offset about the field center that best
re-aligns them to a truth reference catalog. It reproduces the "initial-WCS
source-vs-refcat alignment sweep" the profile says originally found the 180 deg
boresight -- but now as an epoch-by-epoch measurement (the 180 deg was empirically
fit on 2010/2011 SA98; 2006 NGC2298 may differ).

LIMITATION (important): this probe searches only (rotation, scale) about the field
center -- it has NO translation degree of freedom, so it CANNOT detect a pure
pointing/boresight *offset* (a bulk RA/Dec shift), which is the most common seed
defect. On CTIO 2006 the real defect turned out to be exactly such a ~7' pointing
translation: this probe could not see it (it collapsed to the chance-match floor),
and the offset was instead found by a blind astrometry.net solve. Add a (dRA, dDec)
search axis before trusting a null / low-n_match result from this tool.

The four pure functions (rotate_about, scale_about, align_score, search_offset)
are unit-tested in tests/test_ctio_wcs_seed_probe.py and are pure numpy -- NO
lsst import at module top level, so the module imports in a plain venv. All
stack/butler machinery lives inside main() (and the in-stack snippet it runs),
following the repo's "run a snippet inside the stack that returns JSON, then
compute in the venv" pattern (see packages/stips/src/stips/core/stack.py).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------- #
# Pure geometry: rotate/scale sky points about `center` in a local tangent
# frame. The tangent frame is the small-angle gnomonic-ish projection about
# center: x = (ra - ra0) * cos(dec0), y = (dec - dec0), both in degrees. Over a
# ~0.3 deg field this is accurate to well under the 2" match tolerance.
# --------------------------------------------------------------------------- #
def _to_tangent(pts: np.ndarray, center) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(pts, dtype=float)
    ra0, dec0 = center
    cosd = math.cos(math.radians(dec0))
    x = (pts[:, 0] - ra0) * cosd
    y = pts[:, 1] - dec0
    return x, y


def _from_tangent(x: np.ndarray, y: np.ndarray, center) -> np.ndarray:
    ra0, dec0 = center
    cosd = math.cos(math.radians(dec0))
    ra = ra0 + x / cosd
    dec = dec0 + y
    return np.column_stack([ra, dec])


def rotate_about(pts: np.ndarray, d_rot_deg: float, center) -> np.ndarray:
    """Rotate sky points `pts` (array of (ra,dec) deg) by `d_rot_deg` about
    `center`, in the local tangent frame. Returns a new (N,2) array."""
    x, y = _to_tangent(pts, center)
    a = math.radians(d_rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    xr = x * ca - y * sa
    yr = x * sa + y * ca
    return _from_tangent(xr, yr, center)


def scale_about(pts: np.ndarray, d_scale: float, center) -> np.ndarray:
    """Scale sky points `pts` radially about `center` by a fractional factor
    (1 + d_scale) in the local tangent frame. Returns a new (N,2) array."""
    x, y = _to_tangent(pts, center)
    f = 1.0 + d_scale
    return _from_tangent(x * f, y * f, center)


def align_score(src_sky, ref_sky, d_rot_deg: float, d_scale: float, center) -> dict:
    """Apply trial rotation `d_rot_deg` then fractional scale `d_scale` about
    `center` to `src_sky`, nearest-neighbour match each transformed source to
    `ref_sky`, and return {"n_match", "median_sep_arcsec"} for matches within a
    tight 2" radius."""
    from scipy.spatial import cKDTree

    t = rotate_about(src_sky, d_rot_deg, center)
    t = scale_about(t, d_scale, center)

    xs, ys = _to_tangent(t, center)
    xr, yr = _to_tangent(ref_sky, center)
    tree = cKDTree(np.column_stack([xr, yr]))
    dist_deg, _ = tree.query(np.column_stack([xs, ys]))
    sep_arcsec = dist_deg * 3600.0
    matched = sep_arcsec <= 2.0
    n_match = int(matched.sum())
    median = float(np.median(sep_arcsec[matched])) if n_match else float("inf")
    return {"n_match": n_match, "median_sep_arcsec": median}


def search_offset(src_sky, ref_sky, center, rot_grid, scale_grid) -> dict:
    """Grid-search (d_rot_deg, d_scale) over the Cartesian product of
    rot_grid x scale_grid; return the peak {"d_rot_deg","d_scale","n_match",
    "median_sep_arcsec"} maximizing n_match, tie-broken by lowest median_sep."""
    best = None
    best_key = None
    for dr in rot_grid:
        for ds in scale_grid:
            s = align_score(src_sky, ref_sky, float(dr), float(ds), center)
            # maximize n_match, then minimize median_sep (== maximize -median)
            key = (s["n_match"], -s["median_sep_arcsec"])
            if best_key is None or key > best_key:
                best_key = key
                best = {"d_rot_deg": float(dr), "d_scale": float(ds), **s}
    return best


# --------------------------------------------------------------------------- #
# Stack-touching load: run an in-stack snippet that detects bright sources on
# the post_isr_image, projects them through the seed WCS, loads refcat
# positions, and prints JSON. The venv-side driver then runs the pure search.
# --------------------------------------------------------------------------- #

# In-stack snippet. Reads its parameters from environment variables (never
# interpolated into shell text). Prints one JSON line to stdout.
_INSTACK_SNIPPET = r'''
import json, os
import numpy as np
import lsst.geom as geom
from lsst.daf.butler import Butler
from lsst.afw.detection import GaussianPsf
from lsst.afw.table import SourceTable
from lsst.meas.algorithms import SourceDetectionTask, ReferenceObjectLoader

repo = os.environ["PROBE_REPO"]
collection = os.environ["PROBE_COLLECTION"]
exposure_id = int(os.environ["PROBE_VISIT"])
detector = int(os.environ["PROBE_DETECTOR"])
refcat_name = os.environ["PROBE_REFCAT"]
n_bright = int(os.environ.get("PROBE_NBRIGHT", "300"))
radius_deg = float(os.environ.get("PROBE_RADIUS", "0.3"))

butler = Butler(repo)

# --- Find the post_isr_image (dimensioned by exposure, not visit) ---
refs = list(butler.query_datasets(
    "post_isr_image", collections=collection, find_first=False,
    where="instrument='CTIO1m' AND exposure=%d AND detector=%d"
    % (exposure_id, detector),
))
if not refs:
    raise SystemExit("PROBE_ERROR: no post_isr_image for exposure=%d det=%d in %s"
                     % (exposure_id, detector, collection))
exp = butler.get(refs[0])
wcs = exp.getWcs()
if wcs is None:
    raise SystemExit("PROBE_ERROR: post_isr_image has no WCS (seed WCS missing)")

# Field center from the seed WCS at the bbox centre.
bbox = exp.getBBox()
cen_pix = bbox.getCenter()
cen_sky = wcs.pixelToSky(cen_pix)
center = [cen_sky.getRa().asDegrees(), cen_sky.getDec().asDegrees()]

# --- Detect bright sources. Remove sky pedestal so a stdev threshold is
# meaningful, install a simple PSF for the detection smoothing. ---
med = float(np.nanmedian(exp.image.array))
exp.image.array[:] = exp.image.array - med
if exp.getPsf() is None:
    exp.setPsf(GaussianPsf(21, 21, 3.0))

schema = SourceTable.makeMinimalSchema()
det_cfg = SourceDetectionTask.ConfigClass()
det_cfg.thresholdType = "stdev"
det_cfg.thresholdValue = 50.0        # bright sources only
det_cfg.reEstimateBackground = False
det_cfg.doTempLocalBackground = False
det = SourceDetectionTask(schema=schema, config=det_cfg)
table = SourceTable.make(schema)
result = det.run(table, exp)

# Collect footprint peaks (crowded fields blend into few footprints, so use
# every peak), rank by peak value, keep the brightest n_bright.
peaks = []
for src in result.sources:
    fp = src.getFootprint()
    for pk in fp.getPeaks():
        peaks.append((float(pk.getPeakValue()), float(pk.getFx()), float(pk.getFy())))
peaks.sort(key=lambda t: t[0], reverse=True)
peaks = peaks[:n_bright]

src_sky = []
for _val, x, y in peaks:
    sp = wcs.pixelToSky(x, y)
    src_sky.append([sp.getRa().asDegrees(), sp.getDec().asDegrees()])

# --- Load refcat POSITIONS in the field. loadSkyCircle prunes shards by their
# HTM dataId, so passing all shards is fine. Discover a valid flux filter name
# from the first shard's schema (we only need positions, but loadSkyCircle
# requires a filterName). ---
ref_ds = list(butler.query_datasets(refcat_name, collections="*", find_first=False))
if not ref_ds:
    raise SystemExit("PROBE_ERROR: no %s refcat datasets found" % refcat_name)
first = butler.get(ref_ds[0])
flux_fields = [n for n in first.schema.getNames()
               if n.endswith("_flux") and not n.endswith("_fluxErr")]
filt = flux_fields[0][:-5] if flux_fields else None

# loadSkyCircle prunes shards via dataId.region, which requires dimension
# records -- expand each dataId so .region is populated.
loader = ReferenceObjectLoader(
    dataIds=[butler.registry.expandDataId(d.dataId) for d in ref_ds],
    refCats=[butler.getDeferred(d) for d in ref_ds],
    name=refcat_name,
)
ctr = geom.SpherePoint(center[0], center[1], geom.degrees)
loaded = loader.loadSkyCircle(ctr, radius_deg * geom.degrees, filt)
rc = loaded.refCat
ref_ra = np.rad2deg(np.asarray(rc["coord_ra"]))
ref_dec = np.rad2deg(np.asarray(rc["coord_dec"]))

# The refcat is FAR denser than the ~20' FOV needs (thousands of refs in the
# cone), so raw 2" matching is chance-dominated (random floor ~ n_ref/area).
# Keep only the brightest n_ref refs (by flux) so bright-source-to-bright-ref
# matching has a near-zero chance floor and a real transform peak stands out.
n_ref_keep = int(os.environ.get("PROBE_NREF", "400"))
flux = np.asarray(rc[filt + "_flux"]) if filt else np.full(len(ref_ra), np.nan)
finite = np.isfinite(flux) & (flux > 0)
if finite.sum() >= n_ref_keep:
    idx = np.argsort(flux[finite])[::-1][:n_ref_keep]
    keep = np.flatnonzero(finite)[idx]
    ref_ra, ref_dec = ref_ra[keep], ref_dec[keep]
ref_sky = np.column_stack([ref_ra, ref_dec]).tolist()

print("PROBE_JSON:" + json.dumps({
    "center": center,
    "src_sky": src_sky,
    "ref_sky": ref_sky,
    "refcat": refcat_name,
    "flux_filter": filt,
    "n_src": len(src_sky),
    "n_ref": len(ref_sky),
    "run": refs[0].run,
}))
'''


def _run_instack(args) -> dict:
    """Run the in-stack snippet, return its parsed JSON payload."""
    wt = Path(__file__).resolve().parents[2]  # scripts/analysis/.. -> repo root
    stack_dir = Path(args.stack_dir)
    loader = None
    for name in ("loadLSST.zsh", "loadLSST.bash", "loadLSST.sh"):
        if (stack_dir / name).exists():
            loader = stack_dir / name
            break
    if loader is None:
        raise SystemExit(f"No loadLSST script under {stack_dir}")

    obs_ctio_data = wt / "instruments" / "ctio1m" / "obs_ctio1m_data"
    obs_stips = wt / "packages" / "obs_stips"
    instrument_dir = wt / "instruments" / "ctio1m"
    stips_src = wt / "packages" / "stips" / "src"

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(_INSTACK_SNIPPET)
        snippet_path = fh.name

    # Values referenced as "$VAR" in the script text travel via env= so no path
    # metacharacter can expand/inject (mirrors core/stack.py F-018 handling).
    env = {
        **os.environ,
        "PROBE_REPO": str(args.repo),
        "PROBE_COLLECTION": str(args.collection),
        "PROBE_VISIT": str(args.visit),
        "PROBE_DETECTOR": str(args.detector),
        "PROBE_REFCAT": str(args.refcat),
        "PROBE_NBRIGHT": str(args.n_bright),
        "PROBE_NREF": str(args.n_ref),
        "PROBE_RADIUS": str(args.radius),
        "STIPS_LOADER": str(loader),
        "STACK_DIR": str(stack_dir),
        "OBS_CTIO_DATA": str(obs_ctio_data),
        "OBS_STIPS": str(obs_stips),
        "INSTRUMENT_DIR": str(instrument_dir),
        "STIPS_SRC": str(stips_src),
        "SNIPPET": snippet_path,
    }
    script = r'''
cd "$STACK_DIR"
source "$STIPS_LOADER"
setup lsst_distrib
if [ -d "$OBS_CTIO_DATA" ]; then
    setup -r "$OBS_CTIO_DATA" obs_ctio1m_data
fi
setup -r "$OBS_STIPS" obs_stips
export INSTRUMENT_DIR="$INSTRUMENT_DIR"
export PYTHONPATH="${STIPS_SRC}:${PYTHONPATH:-}"
python "$SNIPPET"
'''
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env,
        cwd=str(stack_dir),
    )
    try:
        os.unlink(snippet_path)
    except OSError:
        pass

    payload = None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("PROBE_JSON:"):
            payload = json.loads(line[len("PROBE_JSON:"):])
    if payload is None:
        sys.stderr.write(proc.stdout[-3000:] + "\n---STDERR---\n" + proc.stderr[-3000:] + "\n")
        raise SystemExit(f"in-stack snippet produced no PROBE_JSON (exit {proc.returncode})")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--collection", required=True,
                    help="collection glob holding the post_isr_image")
    ap.add_argument("--visit", type=int, required=True,
                    help="exposure id (post_isr_image is keyed by exposure)")
    ap.add_argument("--detector", type=int, default=0)
    ap.add_argument("--refcat", default="gaia_dr3",
                    help="reference-catalog dataset type (gaia_dr3 for NGC2298; "
                         "the_monster_20250219_local for SA98)")
    ap.add_argument("--n-bright", dest="n_bright", type=int, default=300)
    ap.add_argument("--n-ref", dest="n_ref", type=int, default=400,
                    help="keep only the brightest n_ref refs (collapses the "
                         "chance-match floor from the over-dense refcat cone)")
    ap.add_argument("--radius", type=float, default=0.3,
                    help="refcat cone radius (deg)")
    ap.add_argument("--stack-dir", default=os.environ.get("STACK_DIR"),
                    help="LSST stack dir (defaults to $STACK_DIR); required if unset")
    args = ap.parse_args()

    data = _run_instack(args)
    center = tuple(data["center"])
    src_sky = np.asarray(data["src_sky"], dtype=float)
    ref_sky = np.asarray(data["ref_sky"], dtype=float)

    print(f"# repo={args.repo}")
    print(f"# collection={args.collection}  exposure={args.visit}  detector={args.detector}")
    print(f"# refcat={data['refcat']} (flux_filter={data.get('flux_filter')})  run={data.get('run')}")
    print(f"# field center (seed WCS): RA={center[0]:.6f} Dec={center[1]:.6f}")
    print(f"# n_detected_sources={data['n_src']}  n_refs={data['n_ref']}")
    if src_sky.size == 0 or ref_sky.size == 0:
        raise SystemExit("PROBE_ERROR: empty sources or refs -- cannot search")

    # Baseline (no correction) alignment, for context.
    base = align_score(src_sky, ref_sky, 0.0, 0.0, center)
    print(f"# baseline (d_rot=0, d_scale=0): n_match={base['n_match']} "
          f"median_sep={base['median_sep_arcsec']:.3f}\"")

    rot_grid = np.arange(-30, 30, 0.25)
    scale_grid = np.arange(-0.05, 0.05, 0.0025)
    best = search_offset(src_sky, ref_sky, center, rot_grid, scale_grid)

    print("=" * 64)
    print("PEAK (best re-aligning correction):")
    print(f"  d_rot_deg          = {best['d_rot_deg']:+.3f}")
    print(f"  d_scale            = {best['d_scale']:+.5f}  "
          f"({best['d_scale'] * 100:+.3f}% plate-scale)")
    print(f"  n_match            = {best['n_match']}  "
          f"(of {data['n_src']} sources, {data['n_ref']} refs)")
    print(f"  median_sep_arcsec  = {best['median_sep_arcsec']:.3f}")
    print("=" * 64)
    print("MEASUREMENT_TUPLE:" + json.dumps({
        "d_rot_deg": best["d_rot_deg"],
        "d_scale": best["d_scale"],
        "n_match": best["n_match"],
        "median_sep_arcsec": best["median_sep_arcsec"],
    }))


if __name__ == "__main__":
    main()
