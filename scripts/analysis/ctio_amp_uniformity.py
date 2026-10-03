"""Per-amp background uniformity check on an assembled CTIO image.

Splits a preliminary_visit_image into its four 2032x2032 quadrants (A02 A03 /
A00 A01) and reports median + MAD per amp. Acceptance: the A01 quadrant's MAD is
within TOL_MAD x the median of the other three amps' MADs, and its median is
within TOL_MED ADU of their median. Runs the query inside the stack; STIPS stays
import-free (see core/stack.py).

Usage: python ctio_amp_uniformity.py <config.yaml> <collection> <visit> <band>
"""

import json
import sys

from stips.core import config as cfg_module
from stips.core.stack import run_butler_python_json

TOL_MAD = 2.0  # A01 MAD may be at most 2x the other amps' median MAD
TOL_MED = 30.0  # A01 median within 30 ADU of the other amps' median


def main():
    cfg = cfg_module.load(sys.argv[1])
    collection, visit, band = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    script = f"""
import json, numpy as np
from lsst.daf.butler import Butler
b = Butler({str(cfg.repo)!r})
im = b.get("preliminary_visit_image",
           dataId={{"instrument":"CTIO1m","visit":{visit},"detector":0,"band":{band!r}}},
           collections={collection!r})
a = np.asarray(im.image.array, float); ny, nx = a.shape; h, w = ny//2, nx//2
quads = {{"A02_TL": a[h:,:w], "A03_TR": a[h:,w:], "A00_BL": a[:h,:w], "A01_BR": a[:h,w:]}}
out = {{}}
for k, v in quads.items():
    f = v[np.isfinite(v)]; med = float(np.median(f))
    out[k] = [med, float(np.median(np.abs(f-med)))]
print(json.dumps(out))
"""
    res = run_butler_python_json(script, cfg)
    if res is None:
        print("QUERY FAILED")
        sys.exit(2)
    a01_med, a01_mad = res["A01_BR"]
    others = [v for k, v in res.items() if k != "A01_BR"]
    med_others = sorted(v[0] for v in others)[1]
    mad_others = sorted(v[1] for v in others)[1]
    ok = (a01_mad <= TOL_MAD * mad_others) and (abs(a01_med - med_others) <= TOL_MED)
    print(
        json.dumps(
            {
                "per_amp": res,
                "a01_vs_others": {
                    "a01": [a01_med, a01_mad],
                    "others_median": [med_others, mad_others],
                },
                "PASS": ok,
            },
            indent=1,
        )
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
