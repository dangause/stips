#!/usr/bin/env python
"""Build landolt_catalog_ctio.csv: Landolt standards in the Y4KCam fields observed in 2011.

Inputs are VizieR TSV dumps of the Landolt catalogues and the list of observed
fields with the exact raw OBJECT string of their frames. Output has the
columns of landolt_catalog.csv.

VizieR source discovery (CDS at Strasbourg is unreachable from this machine;
the CfA mirror is used instead, https://vizier.cfa.harvard.edu). The
`/table2` suffixes used in early drafts of the plan do not exist on this
mirror ("Table 'table2' does not exist in catalog"); dropping the suffix and
querying the catalogue id directly works:

    for cat in J/AJ/133/2502 J/AJ/137/4186 J/AJ/146/131; do
      curl -sS -L "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source=$cat&-out.max=unlimited&-out.all" \
        -o "/tmp/$(echo $cat | tr / _).tsv"
    done

Table ids that worked, and what they contributed to FIELDS:
  - J/AJ/133/2502 (Landolt 2007, "phot" table) holds LSE 259, LSS 982, LSE 44,
    WD 0830-535, WD 1056-384, WD 1153-484 and MCT 2019-4339 (and their lettered
    companions within each field).
  - J/AJ/137/4186 (Landolt 2009, "stars" table) holds SA 92 and SA 98.
  - J/AJ/146/131 (Landolt 2013) was queried but is the +50 deg declination
    paper, not a -50 deg paper as the plan assumed; it contains none of our
    southern fields and is not used. No field in FIELDS was dropped: every
    field has at least one match in the other two tables.

Each VizieR TSV dump bundles one or more tables back to back (separated by a
blank line, each preceded by a "#Table ...:" comment). `read_vizier_tsv` only
reads the FIRST table block, which is the one holding the photometry (Vmag)
in all three catalogues above; the RAJ2000/DEJ2000 columns are sexagesimal
strings ("hh mm ss.sss", "+dd mm ss.ss"), so they are converted with
astropy.coordinates.SkyCoord before the numeric cast.

Usage:
    python scripts/analysis/build_landolt_catalog_ctio.py \
        --landolt /tmp/J_AJ_133_2502.tsv /tmp/J_AJ_137_4186.tsv \
        --out scripts/config/landolt_validation/landolt_catalog_ctio.csv
"""
from __future__ import annotations

import argparse
import math

import pandas as pd

# fits_object is the raw OBJECT string (exact, case-sensitive) of the 2011 frames.
FIELDS = [
    {"fits_object": "LSE259", "ra_deg": 253.451, "dec_deg": -56.004},
    {"fits_object": "LSS982", "ra_deg": 122.625, "dec_deg": -40.513},
    {"fits_object": "LSE44", "ra_deg": 208.187, "dec_deg": -48.151},
    {"fits_object": "WD0830-535", "ra_deg": 127.986, "dec_deg": -53.675},
    {"fits_object": "WD1153-484", "ra_deg": 179.012, "dec_deg": -48.678},
    {"fits_object": "WD1056-384", "ra_deg": 164.565, "dec_deg": -38.722},
    {"fits_object": "MCT2019-4339", "ra_deg": 305.706, "dec_deg": -43.492},
    {"fits_object": "SA92 I", "ra_deg": 13.319, "dec_deg": 0.808},
    {"fits_object": "SA98 I", "ra_deg": 103.041, "dec_deg": -0.417},
]
COLUMNS = [
    "star_name",
    "fits_object",
    "ra_deg",
    "dec_deg",
    "V",
    "B_V",
    "U_B",
    "V_R",
    "V_I",
    "B",
    "R",
    "I",
    "V_err",
    "BV_err",
    "VR_err",
    "VI_err",
]


def _sep_arcmin(ra1, dec1, ra2, dec2) -> float:
    d2r = math.pi / 180.0
    c = math.sin(dec1 * d2r) * math.sin(dec2 * d2r) + math.cos(dec1 * d2r) * math.cos(
        dec2 * d2r
    ) * math.cos((ra1 - ra2) * d2r)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 60.0


def select_stars(
    landolt: pd.DataFrame, fields: list[dict], radius_arcmin: float = 10.0
) -> pd.DataFrame:
    rows = []
    for f in fields:
        for _, s in landolt.iterrows():
            if (
                _sep_arcmin(s.ra_deg, s.dec_deg, f["ra_deg"], f["dec_deg"])
                <= radius_arcmin
            ):
                rows.append(
                    {
                        "star_name": s.star_name,
                        "fits_object": f["fits_object"],
                        "ra_deg": s.ra_deg,
                        "dec_deg": s.dec_deg,
                        "V": s.V,
                        "B_V": s.B_V,
                        "U_B": s.U_B,
                        "V_R": s.V_R,
                        "V_I": s.V_I,
                        "B": s.V + s.B_V,
                        "R": s.V - s.V_R,
                        "I": s.V - s.V_I,
                        "V_err": s.V_err,
                        "BV_err": s.BV_err,
                        "VR_err": s.VR_err,
                        "VI_err": s.VI_err,
                    }
                )
    return pd.DataFrame(rows, columns=COLUMNS)


def _extract_first_table_block(path: str) -> list[list[str]]:
    """Return the tab-split rows (header, units, dashes, data...) of the FIRST
    table block in a VizieR asu-tsv dump. VizieR concatenates multiple tables
    in one dump, each preceded by a "#Table ...:" comment and separated from
    the next by a blank line; only the first block is needed here, since in
    the catalogues used by this script it is the one with the photometry.
    """
    with open(path) as fh:
        lines = [line.rstrip("\n") for line in fh]
    # Skip leading comment/blank lines to find the header row.
    idx = 0
    while idx < len(lines) and (lines[idx].startswith("#") or lines[idx].strip() == ""):
        idx += 1
    block = []
    for line in lines[idx:]:
        if line.strip() == "" or line.startswith("#"):
            break
        block.append(line.split("\t"))
    return block


def read_vizier_tsv(path: str) -> pd.DataFrame:
    """Read the first table of a VizieR asu-tsv dump and rename its columns
    to the catalogue's. Handles both the Landolt 2007 ("phot", star name
    already in "Name") and Landolt 2009 ("stars", "SimbadName" is the nicer
    "SA NNN-NNN" form) column layouts.
    """
    rows = _extract_first_table_block(path)
    header, *rest = rows
    header = [h.strip().strip("<>") for h in header]
    # rows[1] is the units row, rows[2] the dashed separator row, rest is data.
    data_rows = rest[2:]
    df = pd.DataFrame([[c.strip() for c in r] for r in data_rows], columns=header)

    rename = {
        "Vmag": "V",
        "e_Vmag": "V_err",
        "B-V": "B_V",
        "e_B-V": "BV_err",
        "U-B": "U_B",
        "e_U-B": "UB_err",
        "V-R": "V_R",
        "e_V-R": "VR_err",
        "V-I": "V_I",
        "e_V-I": "VI_err",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    for c in ("V", "B_V", "U_B", "V_R", "V_I", "V_err", "BV_err", "VR_err", "VI_err"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # A handful of VizieR rows omit the error columns (blank field); match
    # landolt_catalog.csv's convention of 0.0000 for an unreported error
    # rather than propagating NaN.
    for c in ("V_err", "BV_err", "VR_err", "VI_err"):
        df[c] = df[c].fillna(0.0)

    import astropy.units as u
    from astropy.coordinates import SkyCoord

    coords = SkyCoord(df["RAJ2000"], df["DEJ2000"], unit=(u.hourangle, u.deg))
    df["ra_deg"] = coords.ra.deg
    df["dec_deg"] = coords.dec.deg

    if "SimbadName" in df.columns:
        has_simbad = df["SimbadName"].astype(str).str.strip() != ""
        df["star_name"] = df["Name"].astype(str).str.strip()
        df.loc[has_simbad, "star_name"] = (
            df.loc[has_simbad, "SimbadName"].astype(str).str.strip()
        )
    else:
        df["star_name"] = df["Name"].astype(str).str.strip()

    return df.dropna(subset=["ra_deg", "dec_deg", "V"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landolt", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--radius-arcmin", type=float, default=10.0)
    args = ap.parse_args()
    landolt = pd.concat([read_vizier_tsv(p) for p in args.landolt], ignore_index=True)
    out = select_stars(landolt, FIELDS, args.radius_arcmin)
    print(out.groupby("fits_object").size())
    print(out.groupby("fits_object")["V"].agg(["min", "max"]))

    # Match landolt_catalog.csv's formatting: 6 decimals for coordinates,
    # 3 for magnitudes/colours, 4 for their errors.
    out_fmt = out.copy()
    for c in ("ra_deg", "dec_deg"):
        out_fmt[c] = out_fmt[c].map(lambda x: f"{x:.6f}")
    for c in ("V", "B_V", "U_B", "V_R", "V_I", "B", "R", "I"):
        out_fmt[c] = out_fmt[c].map(lambda x: f"{x:.3f}")
    for c in ("V_err", "BV_err", "VR_err", "VI_err"):
        out_fmt[c] = out_fmt[c].map(lambda x: f"{x:.4f}")
    out_fmt.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
