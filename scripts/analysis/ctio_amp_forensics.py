"""Raw-vs-declared amp forensics for the CTIO Y4KCam.

For a raw frame (single 4104x4104 HDU) and the camera yaml, report per amp:
  - stats (median, MAD) of the pixels the yaml DECLARES as that amp's imaging
    data and as its serial/parallel overscan;
  - a scan over all four 2032x2032 quadrant sub-regions of the raw, so a
    misplaced amp's REAL data can be located by matching sky statistics.

This distinguishes a geometry error (A01's real data is elsewhere) from a
hardware anomaly (A01 reads oddly everywhere). Pure numpy + pyyaml; no stack.

Usage: python ctio_amp_forensics.py <raw.fits> <y4kcam.yaml>
"""

import sys

import numpy as np
import yaml
from astropy.io import fits


def _stats(a):
    f = a[np.isfinite(a)]
    med = float(np.median(f)) if f.size else float("nan")
    mad = float(np.median(np.abs(f - med))) if f.size else float("nan")
    return med, mad


def _slice(bbox):
    (x0, y0), (xe, ye) = bbox
    return np.s_[y0 : y0 + ye, x0 : x0 + xe]  # numpy is [row=y, col=x]


def main():
    raw_path, yaml_path = sys.argv[1], sys.argv[2]
    raw = fits.getdata(raw_path, 0).astype(float)
    amps = yaml.safe_load(open(yaml_path))["CCDs"]["CCD0"]["amplifiers"]
    print(f"raw {raw.shape} file={raw_path.split('/')[-1]}\n")
    print(f"{'amp':4} {'declared-data med/MAD':24} {'declared-serialOS med/MAD':26}")
    for name in sorted(amps):
        a = amps[name]
        dmed, dmad = _stats(raw[_slice(a["rawDataBBox"])])
        omed, omad = _stats(raw[_slice(a["rawSerialOverscanBBox"])])
        print(f"{name:4} {dmed:9.1f}/{dmad:<7.1f}        {omed:9.1f}/{omad:<7.1f}")
    print("\nquadrant scan (median/MAD of each 2032x2032 raw sub-region):")
    for qy in (0, 2072):
        for qx in (0, 2072):
            med, mad = _stats(raw[qy : qy + 2032, qx : qx + 2032])
            print(
                f"  raw[{qy}:{qy+2032}, {qx}:{qx+2032}]  med={med:9.1f}  MAD={mad:8.1f}"
            )


if __name__ == "__main__":
    main()
