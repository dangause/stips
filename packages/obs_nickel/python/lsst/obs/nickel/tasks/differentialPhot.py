"""LSST PipelineTask for differential aperture photometry.

Reads pre-computed aperture fluxes from calibrateImage star catalogs,
selects a comparison star ensemble, and produces differential flux
lightcurves. Designed for bright star time-domain science (exoplanet
transits, variable stars) where PSF-fitting fails.
"""

from __future__ import annotations

import logging

import numpy as np

try:
    import lsst.pex.config as pexConfig
    import lsst.pipe.base as pipeBase
    from lsst.daf.butler import DeferredDatasetHandle
    from lsst.pipe.base import connectionTypes as ct

    _HAS_LSST = True
except ImportError:
    _HAS_LSST = False

__all__ = [
    "DifferentialPhotConfig",
    "DifferentialPhotTask",
]

_LOG = logging.getLogger(__name__)

# Valid aperture radii from calibrateImage (best_calib_t071.py)
VALID_APERTURE_RADII = [3.0, 6.0, 9.0, 12.0, 17.0, 25.0, 35.0, 50.0, 70.0]


# ---------------------------------------------------------------------------
# Pure-logic helper functions (testable without LSST stack)
# ---------------------------------------------------------------------------


def _angular_separation_arcsec(ra1_deg, dec1_deg, ra2_rad, dec2_rad):
    """Compute angular separation in arcseconds.

    Parameters
    ----------
    ra1_deg, dec1_deg : float
        First position in degrees.
    ra2_rad, dec2_rad : float
        Second position in radians (as stored in SourceCatalog).
    """
    ra1 = np.radians(ra1_deg)
    dec1 = np.radians(dec1_deg)
    cos_sep = np.sin(dec1) * np.sin(dec2_rad) + np.cos(dec1) * np.cos(
        dec2_rad
    ) * np.cos(ra1 - ra2_rad)
    cos_sep = np.clip(cos_sep, -1.0, 1.0)
    return np.degrees(np.arccos(cos_sep)) * 3600.0


def _find_target(sources, target_ra_deg, target_dec_deg, match_radius_arcsec=2.0):
    """Find the target star in a source catalog by position.

    Returns index into sources list, or None if no match within radius.
    """
    best_idx = None
    best_sep = match_radius_arcsec
    for i, src in enumerate(sources):
        sep = _angular_separation_arcsec(
            target_ra_deg,
            target_dec_deg,
            src["coord_ra"],
            src["coord_dec"],
        )
        if sep < best_sep:
            best_sep = sep
            best_idx = i
    return best_idx


def _select_comparisons(
    sources, target_idx, aperture_col, n_max=10, min_rel_mag=0.5, max_rel_mag=4.0
):
    """Select comparison stars from a source catalog.

    Returns list of indices into sources.
    """
    target_flux = sources[target_idx][aperture_col]
    if target_flux <= 0:
        return []

    # Convert magnitude bounds to flux bounds
    # fainter by min_rel_mag mag -> flux * 10^(-min_rel_mag/2.5)
    max_flux = target_flux * 10 ** (-min_rel_mag / 2.5)
    min_flux = target_flux * 10 ** (-max_rel_mag / 2.5)

    candidates = []
    for i, src in enumerate(sources):
        if i == target_idx:
            continue
        flux = src[aperture_col]
        if flux <= 0 or flux < min_flux or flux > max_flux:
            continue
        # Skip flagged sources
        if src.get("base_PixelFlags_flag_saturatedCenter", False):
            continue
        if src.get("base_PixelFlags_flag_edge", False):
            continue
        if src.get("deblend_nChild", 0) > 0:
            continue
        candidates.append((i, flux))

    # Sort by flux descending (brightest first = highest SNR)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in candidates[:n_max]]


def _compute_differential_flux(target_flux, target_err, comp_fluxes, comp_errs):
    """Compute differential flux = target / sum(comparisons).

    Returns (diff_flux, diff_err) or (None, None) if no comparisons.
    """
    if not comp_fluxes:
        return None, None
    comp_sum = sum(comp_fluxes)
    if comp_sum <= 0:
        return None, None
    diff = target_flux / comp_sum
    # Error propagation: sigma_diff = diff * sqrt((sigma_t/t)^2 + (sigma_c/c_sum)^2)
    comp_err_sum = np.sqrt(sum(e**2 for e in comp_errs))
    diff_err = abs(diff) * np.sqrt(
        (target_err / target_flux) ** 2 + (comp_err_sum / comp_sum) ** 2
    )
    return diff, diff_err


def _normalize_lightcurve(diff_fluxes, diff_errors):
    """Normalize differential flux so median = 1.0.

    Returns (norm_flux, norm_err).
    """
    median = np.median(diff_fluxes)
    if median <= 0:
        median = (
            np.mean(diff_fluxes[diff_fluxes > 0]) if np.any(diff_fluxes > 0) else 1.0
        )
    return diff_fluxes / median, diff_errors / median


def _process_catalogs(
    catalogs,
    visit_table,
    target_ra,
    target_dec,
    aperture_radius,
    match_radius,
    n_comparisons,
    min_comparisons,
    min_rel_mag,
    max_rel_mag,
    min_detection_fraction,
    band_filter,
):
    """Core processing logic (static for testability without Butler).

    Parameters
    ----------
    catalogs : list of (visit_id, list-of-dict)
        Each catalog is a list of dicts with coord_ra, coord_dec, aperture flux, etc.
    visit_table : astropy.table.Table
        Visit metadata table with visit, expMidptMJD, band columns.

    Returns
    -------
    astropy.table.Table
        Differential photometry lightcurve table.
    """
    from astropy.table import Table

    r = aperture_radius
    ap_key = f"{int(r)}_0" if r == int(r) else str(r).replace(".", "_")
    ap_col = f"base_CircularApertureFlux_{ap_key}_instFlux"
    ap_err_col = f"base_CircularApertureFlux_{ap_key}_instFluxErr"

    # Build visit metadata lookup
    visit_mjd = {row["visit"]: row["expMidptMJD"] for row in visit_table}
    visit_band = {}
    if "band" in visit_table.colnames:
        visit_band = {row["visit"]: row["band"] for row in visit_table}

    # Filter by band if specified
    if band_filter:
        catalogs = [
            (vid, cat)
            for vid, cat in catalogs
            if visit_band.get(vid, "") == band_filter
        ]

    if not catalogs:
        return Table()

    # Step 1: Pick reference visit — try candidates sorted by source count
    # (the visit with the most sources may have a bad WCS or be from a
    # fallback config that doesn't include the target)
    sorted_catalogs = sorted(catalogs, key=lambda x: len(x[1]), reverse=True)

    ref_cat = target_idx = None
    comp_indices = []
    for _, cand_cat in sorted_catalogs[:20]:  # Try top 20
        ti = _find_target(cand_cat, target_ra, target_dec, match_radius)
        if ti is None:
            continue
        ci = _select_comparisons(
            cand_cat,
            ti,
            ap_col,
            n_max=n_comparisons * 3,
            min_rel_mag=min_rel_mag,
            max_rel_mag=max_rel_mag,
        )
        if len(ci) >= min_comparisons:
            ref_cat, target_idx, comp_indices = cand_cat, ti, ci
            break

    if target_idx is None:
        _LOG.warning("Target not found in any of the top reference visits")
        return Table()

    if len(comp_indices) < min_comparisons:
        _LOG.warning(
            "Only %d comparisons found (need %d)", len(comp_indices), min_comparisons
        )
        return Table()

    # Get comparison star positions from reference catalog
    comp_positions = [
        (ref_cat[ci]["coord_ra"], ref_cat[ci]["coord_dec"]) for ci in comp_indices
    ]

    # Step 4: Cross-match across all visits, assess stability
    n_visits = len(catalogs)
    comp_detections = [0] * len(comp_indices)
    comp_flux_lists = [[] for _ in range(len(comp_indices))]

    for vid, cat in catalogs:
        for j, (cra, cdec) in enumerate(comp_positions):
            cra_deg = np.degrees(cra)
            cdec_deg = np.degrees(cdec)
            ci = _find_target(cat, cra_deg, cdec_deg, match_radius)
            if ci is not None:
                comp_detections[j] += 1
                comp_flux_lists[j].append(cat[ci][ap_col])

    # Filter by detection fraction and stability
    stable_comps = []
    for j in range(len(comp_indices)):
        frac = comp_detections[j] / n_visits
        if frac < min_detection_fraction:
            continue
        if len(comp_flux_lists[j]) < 2:
            continue
        rms = np.std(comp_flux_lists[j]) / np.mean(comp_flux_lists[j])
        stable_comps.append((j, rms))

    # Sort by RMS (most stable first), take top N
    stable_comps.sort(key=lambda x: x[1])
    final_comp_indices = [j for j, _ in stable_comps[:n_comparisons]]

    if len(final_comp_indices) < min_comparisons:
        _LOG.warning(
            "Only %d stable comparisons (need %d)",
            len(final_comp_indices),
            min_comparisons,
        )
        return Table()

    final_comp_positions = [comp_positions[j] for j in final_comp_indices]
    _LOG.info(
        "Selected %d comparison stars (RMS range: %.4f-%.4f)",
        len(final_comp_indices),
        stable_comps[0][1] if stable_comps else 0,
        (
            stable_comps[min(len(stable_comps) - 1, n_comparisons - 1)][1]
            if stable_comps
            else 0
        ),
    )

    # Step 5: Compute differential flux per visit
    rows = []
    for vid, cat in catalogs:
        mjd = visit_mjd.get(vid, np.nan)
        band = visit_band.get(vid, "")
        # Find target
        ti = _find_target(cat, target_ra, target_dec, match_radius)
        if ti is None:
            continue
        target_flux = cat[ti][ap_col]
        target_err = cat[ti][ap_err_col]
        if target_flux is None or target_flux <= 0:
            continue
        # Find comparisons
        c_fluxes, c_errs = [], []
        for cra, cdec in final_comp_positions:
            ci = _find_target(cat, np.degrees(cra), np.degrees(cdec), match_radius)
            if ci is not None:
                cf = cat[ci][ap_col]
                ce = cat[ci][ap_err_col]
                if cf is not None and cf > 0:
                    c_fluxes.append(cf)
                    c_errs.append(ce if ce else 0.0)
        if len(c_fluxes) < min_comparisons:
            continue
        diff, diff_err = _compute_differential_flux(
            target_flux, target_err, c_fluxes, c_errs
        )
        if diff is None:
            continue
        rows.append(
            {
                "mjd": mjd,
                "band": band,
                "visit": vid,
                "diff_flux": diff,
                "diff_flux_err": diff_err,
                "target_flux": target_flux,
                "comp_sum": sum(c_fluxes),
                "n_comps": len(c_fluxes),
                "aperture_radius_px": aperture_radius,
            }
        )

    if not rows:
        return Table()

    table = Table(rows=rows)
    table.sort("mjd")

    # Step 6: Normalize
    norm, norm_err = _normalize_lightcurve(
        np.array(table["diff_flux"]),
        np.array(table["diff_flux_err"]),
    )
    table["norm_flux"] = norm
    table["norm_flux_err"] = norm_err
    return table


# ---------------------------------------------------------------------------
# LSST PipelineTask (only defined when LSST stack is available)
# ---------------------------------------------------------------------------
if _HAS_LSST:

    class DifferentialPhotConnections(
        pipeBase.PipelineTaskConnections,
        dimensions=("instrument",),
        defaultTemplates={
            "starCatalogName": "single_visit_star_unstandardized",
            "visitTableName": "preliminary_visit_table",
            "outputName": "differential_phot_lightcurve",
        },
    ):
        """Connections for DifferentialPhotTask."""

        starCatalogs = ct.Input(
            doc="Star catalogs from calibrateImage with aperture fluxes.",
            name="{starCatalogName}",
            storageClass="ArrowAstropy",
            dimensions=("instrument", "visit", "detector"),
            multiple=True,
            deferLoad=True,
        )
        visitTable = ct.Input(
            doc="Visit table with MJD and metadata.",
            name="{visitTableName}",
            storageClass="ArrowAstropy",
            dimensions=("instrument",),
        )
        lightcurveTable = ct.Output(
            doc="Differential photometry lightcurve.",
            name="{outputName}_table",
            storageClass="ArrowAstropy",
            dimensions=("instrument",),
        )
        lightcurvePlot = ct.Output(
            doc="Differential photometry lightcurve plot.",
            name="{outputName}_plot",
            storageClass="Plot",
            dimensions=("instrument",),
        )

    class DifferentialPhotConfig(
        pipeBase.PipelineTaskConfig,
        pipelineConnections=DifferentialPhotConnections,
    ):
        """Configuration for DifferentialPhotTask."""

        targetRa = pexConfig.Field(
            dtype=float,
            default=0.0,
            doc="Target right ascension in degrees.",
        )
        targetDec = pexConfig.Field(
            dtype=float,
            default=0.0,
            doc="Target declination in degrees.",
        )
        apertureRadius = pexConfig.Field(
            dtype=float,
            default=17.0,
            doc=(
                "Aperture radius in pixels. Must match one of the radii "
                "configured in calibrateImage: "
                + ", ".join(str(r) for r in VALID_APERTURE_RADII)
            ),
        )
        nComparisons = pexConfig.Field(
            dtype=int,
            default=10,
            doc="Maximum number of comparison stars to use.",
        )
        minComparisons = pexConfig.Field(
            dtype=int,
            default=3,
            doc="Minimum comparison stars required per visit (fewer = skip visit).",
        )
        matchRadius = pexConfig.Field(
            dtype=float,
            default=10.0,
            doc="Cross-match radius in arcseconds. Nickel WCS residuals "
            "can be 5-7 arcsec, so the default is set generously.",
        )
        minRelMag = pexConfig.Field(
            dtype=float,
            default=0.5,
            doc="Comparison stars must be at least this many mag fainter than target.",
        )
        maxRelMag = pexConfig.Field(
            dtype=float,
            default=4.0,
            doc="Comparison stars must be no more than this many mag fainter.",
        )
        minDetectionFraction = pexConfig.Field(
            dtype=float,
            default=0.8,
            doc="Comparison stars must be detected in this fraction of visits.",
        )
        bandFilter = pexConfig.Field(
            dtype=str,
            default="",
            doc="Only process visits in this band (empty = all bands).",
        )
        targetName = pexConfig.Field(
            dtype=str,
            default="",
            doc="Target name for plot title.",
        )

        def validate(self):
            super().validate()
            if self.apertureRadius not in VALID_APERTURE_RADII:
                raise pexConfig.FieldValidationError(
                    self.__class__.apertureRadius,
                    self,
                    f"apertureRadius={self.apertureRadius} not in valid set: "
                    f"{VALID_APERTURE_RADII}",
                )
            if self.nComparisons < self.minComparisons:
                raise pexConfig.FieldValidationError(
                    self.__class__.nComparisons,
                    self,
                    "nComparisons must be >= minComparisons",
                )

    class DifferentialPhotTask(pipeBase.PipelineTask):
        """Compute differential aperture photometry from calibrateImage catalogs."""

        ConfigClass = DifferentialPhotConfig
        _DefaultName = "differentialPhot"

        @property
        def _ap_key(self):
            """Aperture radius formatted as column key fragment (e.g. '17_0')."""
            r = self.config.apertureRadius
            if r == int(r):
                return f"{int(r)}_0"
            return str(r).replace(".", "_")

        def runQuantum(self, butlerQC, inputRefs, outputRefs):
            """Load catalogs from Butler, process, write outputs."""
            visit_table = butlerQC.get(inputRefs.visitTable)

            # Load all star catalogs with visit IDs
            catalogs = []
            for ref in inputRefs.starCatalogs:
                visit_id = ref.dataId.get("visit")
                try:
                    cat = butlerQC.get(ref)
                    if isinstance(cat, DeferredDatasetHandle):
                        cat = cat.get()
                except Exception:
                    _LOG.warning("Failed to load catalog for visit %s", visit_id)
                    continue
                # Convert astropy Table to list of dicts for processing
                ap_col = f"base_CircularApertureFlux_{self._ap_key}_instFlux"
                ap_err_col = f"base_CircularApertureFlux_{self._ap_key}_instFluxErr"
                records = []
                for row in cat:
                    records.append(
                        {
                            "coord_ra": row["coord_ra"],
                            "coord_dec": row["coord_dec"],
                            ap_col: row[ap_col],
                            ap_err_col: row[ap_err_col],
                            "base_PixelFlags_flag_saturatedCenter": row[
                                "base_PixelFlags_flag_saturatedCenter"
                            ],
                            "base_PixelFlags_flag_edge": row[
                                "base_PixelFlags_flag_edge"
                            ],
                            "deblend_nChild": row["deblend_nChild"],
                        }
                    )
                catalogs.append((visit_id, records))

            if not catalogs:
                raise pipeBase.NoWorkFound("No star catalogs loaded.")

            result_table = _process_catalogs(
                catalogs=catalogs,
                visit_table=visit_table,
                target_ra=self.config.targetRa,
                target_dec=self.config.targetDec,
                aperture_radius=self.config.apertureRadius,
                match_radius=self.config.matchRadius,
                n_comparisons=self.config.nComparisons,
                min_comparisons=self.config.minComparisons,
                min_rel_mag=self.config.minRelMag,
                max_rel_mag=self.config.maxRelMag,
                min_detection_fraction=self.config.minDetectionFraction,
                band_filter=self.config.bandFilter,
            )

            if len(result_table) == 0:
                raise pipeBase.NoWorkFound(
                    "No differential photometry measurements produced."
                )

            fig = self._make_plot(result_table)
            butlerQC.put(result_table, outputRefs.lightcurveTable)
            butlerQC.put(fig, outputRefs.lightcurvePlot)

        def _make_plot(self, table):
            """Generate differential photometry lightcurve plot."""
            import matplotlib.pyplot as plt
            from lsst.obs.nickel.plotting import (
                FIGURE_SIZE,
                format_lightcurve_axes,
                plot_lightcurve_band,
                publication_style,
                set_title,
                sort_bands,
            )

            with publication_style():
                fig, ax = plt.subplots(figsize=FIGURE_SIZE)
                bands = sort_bands(set(table["band"]))
                for b in bands:
                    mask = table["band"] == b
                    if not np.any(mask):
                        continue
                    plot_lightcurve_band(
                        ax,
                        table["mjd"][mask],
                        table["norm_flux"][mask],
                        table["norm_flux_err"][mask],
                        b,
                        count=int(np.sum(mask)),
                    )
                ax.axhline(y=1.0, color="0.6", ls="--", lw=0.8, alpha=0.6, zorder=0)
                format_lightcurve_axes(ax, ylabel="Normalized Flux", invert_y=False)
                name = self.config.targetName or "Differential Photometry"
                set_title(ax, name, subtitle="Differential Aperture Photometry")
                ax.legend(loc="best")
                fig.tight_layout()
            return fig

else:
    # Stub classes when LSST stack is not available (for testing)
    DifferentialPhotConnections = None
    DifferentialPhotConfig = None
    DifferentialPhotTask = None
