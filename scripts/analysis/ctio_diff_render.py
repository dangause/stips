"""Render science + difference triptychs for CTIO DIA QA.

For each (visit, band, diff_run) it loads difference_image (diff run) and
preliminary_visit_image (processCcd parent) and saves a 2-panel PNG: science
(gray, zscale+asinh) and difference (RdBu, symmetric at the 98th percentile).
Runs in the stack; STIPS stays import-free.

Usage: python ctio_diff_render.py <config.yaml> <sci_collection> <diff_run> <outdir> <visit:band> [visit:band ...]
"""

import sys

from stips.core import config as cfg_module
from stips.core.stack import run_butler_python


def main():
    cfg = cfg_module.load(sys.argv[1])
    sci_col, diff_run, outdir = sys.argv[2], sys.argv[3], sys.argv[4]
    pairs = [p.split(":") for p in sys.argv[5:]]
    targets = [{"visit": int(v), "band": bd} for v, bd in pairs]
    script = f"""
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from astropy.visualization import ZScaleInterval, ImageNormalize, AsinhStretch
from lsst.daf.butler import Butler
b = Butler({str(cfg.repo)!r}); z = ZScaleInterval()
for t in {targets!r}:
    did = {{"instrument":"CTIO1m","visit":t["visit"],"detector":0,"band":t["band"]}}
    diff = b.get("difference_image", dataId=did, collections={diff_run!r})
    try: sci = b.get("preliminary_visit_image", dataId=did, collections={sci_col!r})
    except Exception: sci = None
    d = np.asarray(diff.image.array, float); fin = d[np.isfinite(d)]
    fig, ax = plt.subplots(1, 2, figsize=(9, 4.5))
    if sci is not None:
        s = np.asarray(sci.image.array, float); sf = s[np.isfinite(s)]; lo, hi = z.get_limits(sf)
        ax[0].imshow(s, origin="lower", cmap="gray", norm=ImageNormalize(vmin=lo, vmax=hi, stretch=AsinhStretch()))
    ax[0].set_title(f"science v{{t['visit']}} {{t['band']}}", fontsize=9)
    sc = np.nanpercentile(np.abs(fin), 98)
    ax[1].imshow(d, origin="lower", cmap="RdBu_r", norm=ImageNormalize(vmin=-sc, vmax=sc))
    ax[1].set_title(f"difference (+/-{{sc:.0f}})  med={{np.nanmedian(fin):.1f}}", fontsize=8)
    for a in ax: a.set_xticks([]); a.set_yticks([])
    fig.tight_layout(); fig.savefig(f"{outdir}/diff_v{{t['visit']}}_{{t['band']}}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
print("rendered", len({targets!r}))
"""
    print(run_butler_python(script, cfg)[-500:])


if __name__ == "__main__":
    main()
