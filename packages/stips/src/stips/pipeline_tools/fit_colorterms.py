#!/usr/bin/env python
"""Fit reference-catalog -> instrument color terms and emit a ``colorterms.py``.

Framework tool (``stips-colorterms-fit``). This is the instrument-neutral
extraction of the former ``obs-nickel-colorterms`` scripts: the color-term
*fitting math* and the ``ColortermDict`` config *emitter* are framework code
parameterized by the active instrument profile, while an instrument's *fitted*
color terms live under its own tree at ``instruments/<name>/configs/colorterms.py``
(the per-instrument file of the tiering contract; see
``packages/obs_stips/instrument_defaults/README.md``).

What it produces
----------------
The output is exactly the drop-in ``config.data = { "<ref>*": ColortermDict(...) }``
file that ``instruments/<name>/configs/colorterms.py`` must contain -- one
``Colorterm(primary=..., secondary=..., c0=, c1=, c2=)`` per band. The stack
applies ``m_instrument = m_primary + c0 + c1*(primary - secondary) + c2*(...)^2``.
``c0`` is absorbed by ``calibrateImage``'s per-visit photometric zeropoint; the
``c1`` (color) slope is what removes color-dependent systematics.

Fitting algorithms (unchanged from the Nickel originals)
--------------------------------------------------------
* **linear/quadratic least squares** (``--fit linear``): for each band, least-
  squares fit ``target = primary + c0 + c1*color (+ c2*color^2)`` against matched
  standard-star photometry. This is the algorithm that produced the reference
  Nickel ``ps1*`` block (Landolt standards), verbatim.
* **spline -> polynomial** (``--from-spline-dir``): read per-band spline YAMLs
  (the synthetic/empirical workflow output), approximate each spline with a
  low-order polynomial in magnitude space, and emit the same config -- verbatim
  from the former ``convert_to_lsst_colorterms.py``.

Parameterization
----------------
The instrument *name* (config header) comes from the active profile
(``INSTRUMENT_DIR``), overridable with ``--instrument``. The reference-catalog
key (``ps1*`` / ``gaia*`` / ``*monster*``) and the per-band color definition
(which reference magnitudes form ``primary``/``secondary``) are CLI arguments
whose defaults reproduce the current Nickel PS1 fit. A fork supplies its own
matched photometry and (if its bands differ) its own ``--color`` definitions.

Producing color terms for a NEW instrument
------------------------------------------
1. Match standard-star reference magnitudes (PS1/Gaia/...) to your instrument's
   calibrated magnitudes for a set of standards; write them to a table with one
   column per reference magnitude and one per instrument band.
2. Run ``stips-colorterms-fit --matched <table> --ref-catalog ps1 \
   --out instruments/<name>/configs/colorterms.py`` (add ``--color`` overrides if
   your band -> color mapping differs from the Nickel default).
3. Review the emitted coefficients and residual RMS, then commit the file.

Record the exact invocation + inputs in ``instruments/<name>/colorterms/README.md``
(see ``instruments/nickel/colorterms/README.md``). Nothing here is Nickel-
specific: a fork reuses this tool unchanged and only stores its own fitted file
and recipe.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# ------------------------------ pure helpers ---------------------------
# numpy is a hard dependency; scipy / yaml / pandas / stips_refcats are
# imported lazily so ``--help`` and the unit tests run in a plain venv.
import numpy as np

# Reference-catalog short name -> ColortermDict key (the wildcard the stack
# matches refcat dataset names against).
REF_CATALOG_KEYS: Dict[str, str] = {
    "ps1": "ps1*",
    "gaia": "gaia*",
    "monster": "*monster*",
}

# band -> (primary, secondary) reference magnitudes. Default reproduces the
# reference Nickel PS1 -> B/V/R/I color definitions (the live ``ps1*`` block).
DEFAULT_PS1_COLORS: Dict[str, Tuple[str, str]] = {
    "B": ("gMeanPSFMag", "rMeanPSFMag"),
    "V": ("gMeanPSFMag", "rMeanPSFMag"),
    "R": ("rMeanPSFMag", "iMeanPSFMag"),
    "I": ("iMeanPSFMag", "rMeanPSFMag"),
}


def fit_linear_colorterm(
    primary: Sequence[float],
    secondary: Sequence[float],
    target: Sequence[float],
    degree: int = 1,
) -> Tuple[float, float, float]:
    """Least-squares fit ``target = primary + c0 + c1*color (+ c2*color^2)``.

    ``color = primary - secondary`` (all magnitudes). Returns ``(c0, c1, c2)``
    with ``c2 == 0.0`` for ``degree == 1``. This is the verbatim algorithm from
    the reference Landolt PS1 fit, generalized to an optional quadratic term.
    """
    primary = np.asarray(primary, dtype=float)
    secondary = np.asarray(secondary, dtype=float)
    target = np.asarray(target, dtype=float)
    color = primary - secondary
    rhs = target - primary

    good = np.isfinite(color) & np.isfinite(rhs)
    color = color[good]
    rhs = rhs[good]
    if len(color) <= degree:
        raise ValueError(
            f"Not enough finite points ({len(color)}) for a degree-{degree} fit"
        )

    if degree == 1:
        A = np.vstack([np.ones_like(color), color]).T
        (c0, c1), *_ = np.linalg.lstsq(A, rhs, rcond=None)
        return float(c0), float(c1), 0.0
    if degree == 2:
        A = np.vstack([np.ones_like(color), color, color**2]).T
        (c0, c1, c2), *_ = np.linalg.lstsq(A, rhs, rcond=None)
        return float(c0), float(c1), float(c2)
    raise ValueError(f"degree must be 1 or 2, got {degree}")


def colorterm_rms(
    primary: Sequence[float],
    secondary: Sequence[float],
    target: Sequence[float],
    c0: float,
    c1: float,
    c2: float = 0.0,
) -> float:
    """RMS of ``primary + c0 + c1*color + c2*color^2 - target`` (mag)."""
    primary = np.asarray(primary, dtype=float)
    secondary = np.asarray(secondary, dtype=float)
    target = np.asarray(target, dtype=float)
    color = primary - secondary
    model = primary + c0 + c1 * color + c2 * color**2
    return float(np.std(model - target))


# ------------------------ spline -> polynomial path --------------------
# Preserved verbatim from the former empirical fitter + convert script so the
# synthetic/empirical (spline) workflow keeps producing the same config.


class ColortermSpline:
    """A spline-based color term transformation (clamped cubic spline)."""

    def __init__(
        self,
        source_name,
        target_name,
        primary_field,
        secondary_field,
        band_field,
        nodes,
        spline_values,
        flux_offset=0.0,
    ):
        from scipy.interpolate import CubicSpline

        self.source_name = source_name
        self.target_name = target_name
        self.primary_field = primary_field
        self.secondary_field = secondary_field
        self.band_field = band_field
        self.nodes = np.array(nodes)
        self.spline_values = np.array(spline_values)
        self.flux_offset = flux_offset
        self.spline = CubicSpline(self.nodes, self.spline_values, bc_type="clamped")


def polynomial_from_spline(
    nodes: Sequence[float], values: Sequence[float], degree: int = 2
) -> Tuple[float, float, float]:
    """Approximate a flux-ratio spline with a magnitude-space polynomial.

    Verbatim from ``convert_to_lsst_colorterms.fit_polynomial_to_spline``:
    evaluate the clamped cubic spline densely, convert the multiplicative flux
    corrections to additive magnitudes (``-2.5*log10``), fit a ``degree``
    polynomial, and return ``(c0, c1, c2)`` (``c2 == 0`` for degree 1).
    """
    from scipy.interpolate import CubicSpline

    spline = CubicSpline(nodes, values, bc_type="clamped")
    colors = np.linspace(nodes[0], nodes[-1], 100)
    corrections = spline(colors)
    mag_corrections = -2.5 * np.log10(corrections)
    coeffs = np.polyfit(colors, mag_corrections, degree)
    lsst_order = coeffs[::-1]  # [c0, c1, c2, ...]
    c0 = float(lsst_order[0])
    c1 = float(lsst_order[1]) if len(lsst_order) > 1 else 0.0
    c2 = float(lsst_order[2]) if len(lsst_order) > 2 else 0.0
    return c0, c1, c2


# ------------------------------ config emitter -------------------------


class ColortermEntry:
    """One band's fitted color term: primary/secondary refs + c0/c1/c2."""

    def __init__(
        self,
        band: str,
        primary: str,
        secondary: str,
        c0: float,
        c1: float,
        c2: float = 0.0,
        comment: str = "",
    ):
        self.band = band
        self.primary = primary
        self.secondary = secondary
        self.c0 = c0
        self.c1 = c1
        self.c2 = c2
        self.comment = comment


def render_colorterms_config(
    entries: List[ColortermEntry],
    ref_key: str,
    instrument: str,
    header_comment: str = "",
) -> str:
    """Render a drop-in ``instruments/<name>/configs/colorterms.py`` file.

    ``ref_key`` is the ColortermDict wildcard (e.g. ``"ps1*"``). The output
    format matches the reference Nickel ``colorterms.py`` exactly and validates
    in the stack (``config.data`` of ``ColortermDict``/``Colorterm``).
    """
    lines: List[str] = []
    lines.append(f"# {instrument} color terms -- fit by stips-colorterms-fit.")
    if header_comment:
        for cl in header_comment.splitlines():
            lines.append(f"# {cl}" if cl else "#")
    lines.append("from lsst.pipe.tasks.colorterms import Colorterm, ColortermDict")
    lines.append("")
    lines.append("config.data = {")
    lines.append(f'    "{ref_key}": ColortermDict(')
    lines.append("        data={")
    for e in entries:
        if e.comment:
            for cl in e.comment.splitlines():
                lines.append(f"            # {cl}")
        lines.append(f'            "{e.band}": Colorterm(')
        lines.append(f'                primary="{e.primary}",')
        lines.append(f'                secondary="{e.secondary}",')
        lines.append(f"                c0={e.c0:.6f},")
        lines.append(f"                c1={e.c1:.6f},")
        lines.append(f"                c2={e.c2:.6f},")
        lines.append("            ),")
    lines.append("        }")
    lines.append("    ),")
    lines.append("}")
    lines.append("# ruff: noqa: F821")
    return "\n".join(lines) + "\n"


# ------------------------------- input IO ------------------------------


def _read_table(path: str):
    """Read a matched-photometry table (CSV/FITS/parquet/ECSV) as a dict.

    Returns a mapping ``column -> numpy array``. ``pandas``/``astropy`` are
    imported lazily.
    """
    import os

    path = os.path.expanduser(path)
    if path.lower().endswith((".csv", ".txt")):
        import pandas as pd

        df = pd.read_csv(path)
        return {c: np.asarray(df[c].values) for c in df.columns}
    from astropy.table import Table

    tbl = Table.read(path)
    return {c: np.asarray(tbl[c]) for c in tbl.colnames}


def fit_from_matched(
    table: Dict[str, "np.ndarray"],
    bands: Sequence[str],
    colors: Dict[str, Tuple[str, str]],
    degree: int = 1,
) -> List[ColortermEntry]:
    """Fit one linear/quadratic color term per band from a matched table.

    ``table`` maps column name -> array (reference mags + one column per band).
    ``colors[band] = (primary_col, secondary_col)``. Emits a ``ColortermEntry``
    per band with the fitted coefficients (comment records the residual RMS).
    """
    entries: List[ColortermEntry] = []
    for band in bands:
        if band not in colors:
            raise ValueError(
                f"No color definition for band '{band}'; pass --color {band}:PRIM:SEC"
            )
        prim_col, sec_col = colors[band]
        for col in (prim_col, sec_col, band):
            if col not in table:
                raise ValueError(f"Column '{col}' not in table (have: {sorted(table)})")
        primary = table[prim_col]
        secondary = table[sec_col]
        target = table[band]
        c0, c1, c2 = fit_linear_colorterm(primary, secondary, target, degree=degree)
        rms = colorterm_rms(primary, secondary, target, c0, c1, c2)
        entries.append(
            ColortermEntry(
                band=band,
                primary=prim_col,
                secondary=sec_col,
                c0=c0,
                c1=c1,
                c2=c2,
                comment=f"{band}: color {prim_col}-{sec_col}, residual RMS {rms:.3f} mag",
            )
        )
    return entries


def fit_from_spline_dir(directory: str, degree: int = 2) -> List[ColortermEntry]:
    """Convert per-band spline YAMLs in a directory into ``ColortermEntry``s.

    Each YAML carries ``primary_field``/``secondary_field``/``band_field``/
    ``nodes``/``spline_values`` (the synthetic/empirical workflow output). The
    band name is parsed from ``band_field`` (``<sys>_<band>_flux``). Reference
    field names keep whatever the YAML stored (stripped of a trailing ``_flux``).
    """
    import glob
    import os

    import yaml

    entries: List[ColortermEntry] = []
    for yml in sorted(glob.glob(os.path.join(os.path.expanduser(directory), "*.yaml"))):
        with open(yml) as f:
            data = yaml.safe_load(f)
        band_field = data["band_field"]  # e.g. nickel_B_flux
        parts = band_field.split("_")
        band = parts[1] if len(parts) >= 3 else band_field
        c0, c1, c2 = polynomial_from_spline(
            data["nodes"], data["spline_values"], degree=degree
        )
        prim = str(data["primary_field"]).replace("_flux", "")
        sec = str(data["secondary_field"]).replace("_flux", "")
        entries.append(
            ColortermEntry(
                band=band,
                primary=prim,
                secondary=sec,
                c0=c0,
                c1=c1,
                c2=c2,
                comment=f"{band}: polynomial approximation of spline fit ({os.path.basename(yml)})",
            )
        )
    return entries


def query_ps1_matched(
    catalog: Dict[str, "np.ndarray"],
    bands: Sequence[str],
    exclude: Sequence[str] = (),
) -> Dict[str, "np.ndarray"]:
    """Match standards (ra_deg/dec_deg + band mags) to PS1 DR2 mean PSF mags.

    Reproduces the reference Landolt PS1 workflow: for each standard, query the
    single PS1 DR2 mean-object cone (5 arcsec) via ``stips_refcats.ps1`` and keep
    the nearest positive g/r/i match. Requires network + the refcats package.
    Returns a matched table (``gMeanPSFMag``/``rMeanPSFMag``/``iMeanPSFMag`` +
    one column per band) ready for :func:`fit_from_matched`.
    """
    from stips_refcats.ps1 import _query_ps1_mean

    names = catalog.get("star_name")
    ra = catalog["ra_deg"]
    dec = catalog["dec_deg"]
    exclude = set(exclude)

    cols: Dict[str, List[float]] = {
        "gMeanPSFMag": [],
        "rMeanPSFMag": [],
        "iMeanPSFMag": [],
        **{b: [] for b in bands},
    }
    for i in range(len(ra)):
        if names is not None and str(names[i]) in exclude:
            continue
        d = _query_ps1_mean(float(ra[i]), float(dec[i]), radius_deg=5.0 / 3600.0)
        d = d[(d.gMeanPSFMag > 0) & (d.rMeanPSFMag > 0) & (d.iMeanPSFMag > 0)]
        if len(d) == 0:
            continue
        dd = (d.raMean - float(ra[i])) ** 2 + (d.decMean - float(dec[i])) ** 2
        m = d.loc[dd.idxmin()]
        cols["gMeanPSFMag"].append(float(m.gMeanPSFMag))
        cols["rMeanPSFMag"].append(float(m.rMeanPSFMag))
        cols["iMeanPSFMag"].append(float(m.iMeanPSFMag))
        for b in bands:
            cols[b].append(float(catalog[b][i]))
    return {k: np.asarray(v, dtype=float) for k, v in cols.items()}


# ------------------------------- CLI -----------------------------------


def _parse_color_overrides(items: Optional[List[str]]) -> Dict[str, Tuple[str, str]]:
    """Parse repeatable ``--color BAND:PRIMARY:SECONDARY`` into a mapping."""
    out: Dict[str, Tuple[str, str]] = {}
    for it in items or []:
        parts = it.split(":")
        if len(parts) != 3:
            raise ValueError(f"--color must be BAND:PRIMARY:SECONDARY, got '{it}'")
        band, prim, sec = parts
        out[band] = (prim, sec)
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Fit reference-catalog -> instrument color terms and emit a drop-in "
            "instruments/<name>/configs/colorterms.py (instrument-neutral; "
            "parameterized by the active profile)."
        )
    )
    ap.add_argument(
        "--instrument",
        default=None,
        help="Instrument name for the config header (default: active profile name).",
    )
    ap.add_argument(
        "--ref-catalog",
        choices=sorted(REF_CATALOG_KEYS),
        default="ps1",
        help="Reference catalog; sets the ColortermDict key (default: ps1 -> 'ps1*').",
    )
    ap.add_argument(
        "--ref-key",
        default=None,
        help="Override the ColortermDict wildcard key (default: from --ref-catalog).",
    )
    ap.add_argument(
        "--bands",
        nargs="+",
        default=["B", "V", "R", "I"],
        help="Instrument bands to fit (default: B V R I).",
    )
    ap.add_argument(
        "--fit",
        choices=["linear"],
        default="linear",
        help="Fitting method for --matched/--landolt-catalog input (default: linear).",
    )
    ap.add_argument(
        "--degree",
        type=int,
        choices=[1, 2],
        default=1,
        help="Polynomial degree for the linear fit (1=color slope, 2=quadratic).",
    )
    ap.add_argument(
        "--color",
        action="append",
        metavar="BAND:PRIMARY:SECONDARY",
        help="Per-band color definition override (repeatable). Default: Nickel PS1.",
    )

    # Input sources (mutually exclusive).
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--matched",
        default=None,
        help="Pre-matched photometry table (CSV/FITS/parquet): ref mags + one column per band.",
    )
    src.add_argument(
        "--landolt-catalog",
        default=None,
        help="Standards catalog (ra_deg/dec_deg + band mags); query PS1 per star (needs network+stack).",
    )
    src.add_argument(
        "--from-spline-dir",
        default=None,
        help="Directory of per-band spline YAMLs to convert (synthetic/empirical workflow).",
    )
    ap.add_argument(
        "--exclude",
        nargs="*",
        default=["SA 109-199"],
        help="star_name(s) to drop (--landolt-catalog mode; default: SA 109-199).",
    )

    ap.add_argument(
        "--out",
        default=None,
        help="Output colorterms.py path (default: stdout).",
    )
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    from stips.pipeline_tools._profile_resolve import resolve_instrument_name

    instrument = resolve_instrument_name(args.instrument)
    ref_key = args.ref_key or REF_CATALOG_KEYS[args.ref_catalog]

    colors = dict(DEFAULT_PS1_COLORS)
    colors.update(_parse_color_overrides(args.color))

    if args.from_spline_dir:
        entries = fit_from_spline_dir(args.from_spline_dir, degree=args.degree + 1)
        header = "Polynomial approximation of spline color terms."
    else:
        if args.landolt_catalog:
            catalog = _read_table(args.landolt_catalog)
            table = query_ps1_matched(catalog, args.bands, exclude=args.exclude)
        else:
            table = _read_table(args.matched)
        n = len(next(iter(table.values()))) if table else 0
        print(
            f"fitting on {n} matched stars ({args.ref_catalog}, degree {args.degree})"
        )
        entries = fit_from_matched(table, args.bands, colors, degree=args.degree)
        header = (
            f"Empirically fit against {args.ref_catalog.upper()} standards. "
            "c0 is absorbed by the per-visit zeropoint; c1 removes color systematics."
        )

    content = render_colorterms_config(
        entries, ref_key=ref_key, instrument=instrument, header_comment=header
    )
    for e in entries:
        print(f"  {e.band}: c0={e.c0:+.4f} c1={e.c1:+.4f} c2={e.c2:+.4f}")

    if args.out:
        import os

        out = os.path.expanduser(args.out)
        with open(out, "w") as f:
            f.write(content)
        print(f"Wrote {out}")
    else:
        print()
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
