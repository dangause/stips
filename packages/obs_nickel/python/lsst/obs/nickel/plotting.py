"""Publication-quality plotting utilities for Nickel telescope lightcurves.

This module provides shared styling constants and helper functions used by
all lightcurve plotting code (PipelineTasks and CLI tools) to produce
consistent, journal-ready figures.

Usage in PipelineTasks (restores rcParams after)::

    from lsst.obs.nickel.plotting import (
        publication_style, format_lightcurve_axes,
        plot_lightcurve_band, set_title,
    )

    with publication_style():
        fig, ax = plt.subplots(figsize=FIGURE_SIZE)
        plot_lightcurve_band(ax, mjd, mag, mag_err, "r", count=len(mjd))
        format_lightcurve_axes(ax)
        set_title(ax, "SN 2023ixf")
        fig.tight_layout()

Usage in CLI scripts::

    from lsst.obs.nickel.plotting import apply_publication_style, ...
    apply_publication_style()
"""

from __future__ import annotations

import contextlib

import matplotlib as mpl
import matplotlib.ticker as mticker

__all__ = [
    "BAND_STYLE",
    "DEFAULT_STYLE",
    "FIGURE_SIZE",
    "PUBLICATION_RCPARAMS",
    "apply_publication_style",
    "format_lightcurve_axes",
    "get_band_style",
    "plot_lightcurve_band",
    "publication_style",
    "set_title",
    "sort_bands",
]

# ---------------------------------------------------------------------------
# Band styling: colors, markers, labels, and zorder (ordered blue → red)
# ---------------------------------------------------------------------------

BAND_STYLE = {
    "b": {"color": "#2166ac", "marker": "o", "label": "B", "zorder": 5},
    "v": {"color": "#4daf4a", "marker": "s", "label": "V", "zorder": 4},
    "r": {"color": "#e41a1c", "marker": "D", "label": "R", "zorder": 3},
    "i": {"color": "#8b0000", "marker": "^", "label": "I", "zorder": 2},
}

DEFAULT_STYLE = {"color": "black", "marker": "o", "label": "?", "zorder": 1}

# Standard figure size (inches) — fits journal double-column and looks good on screen
FIGURE_SIZE = (8, 5)

# Wavelength-ordered band list for consistent legend ordering
_BAND_ORDER = list(BAND_STYLE.keys())

# ---------------------------------------------------------------------------
# Publication rcParams (ApJ / journal style)
# ---------------------------------------------------------------------------

PUBLICATION_RCPARAMS = {
    # Font: serif (LaTeX-like) without requiring a TeX installation
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Computer Modern Roman"],
    "font.size": 12,
    "mathtext.fontset": "dejavuserif",
    # Axes
    "axes.labelsize": 14,
    "axes.titlesize": 14,
    "axes.linewidth": 1.2,
    "axes.labelpad": 6,
    # Tick marks — inward on all four sides (ApJ convention)
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "xtick.major.size": 6,
    "xtick.minor.size": 3,
    "ytick.major.size": 6,
    "ytick.minor.size": 3,
    "xtick.major.width": 1.0,
    "xtick.minor.width": 0.7,
    "ytick.major.width": 1.0,
    "ytick.minor.width": 0.7,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "xtick.top": True,
    "ytick.right": True,
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    # Legend
    "legend.fontsize": 11,
    "legend.framealpha": 0.9,
    "legend.edgecolor": "0.8",
    "legend.fancybox": False,
    # Lines and error bars
    "lines.linewidth": 1.5,
    "lines.markersize": 7,
    "errorbar.capsize": 3,
    # Figure
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    # Grid off by default — we add it explicitly for control
    "axes.grid": False,
}


# ---------------------------------------------------------------------------
# Style application
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def publication_style():
    """Context manager that temporarily applies publication rcParams.

    Use this in PipelineTasks so global matplotlib state is restored
    after the plot is created.
    """
    with mpl.rc_context(PUBLICATION_RCPARAMS):
        yield


def apply_publication_style():
    """Apply publication rcParams globally.

    Use this in standalone CLI scripts where you control the entire process.
    """
    mpl.rcParams.update(PUBLICATION_RCPARAMS)


# ---------------------------------------------------------------------------
# Band helpers
# ---------------------------------------------------------------------------


def get_band_style(band: str) -> dict:
    """Return a copy of the style dict for a given band name.

    Parameters
    ----------
    band : `str`
        Band name (e.g. ``"r"``, ``"i"``).

    Returns
    -------
    style : `dict`
        Keys: ``color``, ``marker``, ``label``, ``zorder``.
    """
    return BAND_STYLE.get(band.lower(), DEFAULT_STYLE).copy()


def sort_bands(bands):
    """Sort band names in wavelength order (blue → red).

    Parameters
    ----------
    bands : iterable of `str`
        Band names.

    Returns
    -------
    sorted_bands : `list` of `str`
        Bands sorted by wavelength.
    """
    return sorted(
        bands,
        key=lambda b: _BAND_ORDER.index(b.lower()) if b.lower() in _BAND_ORDER else 99,
    )


# ---------------------------------------------------------------------------
# Reusable plotting functions
# ---------------------------------------------------------------------------


def format_lightcurve_axes(
    ax,
    ylabel="Apparent Magnitude (mag)",
    xlabel="Modified Julian Date (MJD)",
    invert_y=True,
    show_grid=True,
):
    """Apply publication formatting to lightcurve axes.

    Parameters
    ----------
    ax : `matplotlib.axes.Axes`
        The axes to format.
    ylabel : `str`
        Y-axis label.
    xlabel : `str`
        X-axis label.
    invert_y : `bool`
        Invert y-axis (brighter = lower magnitude at top).
    show_grid : `bool`
        Show subtle grid lines.
    """
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if invert_y:
        ax.invert_yaxis()
    ax.minorticks_on()
    # Use plain float notation instead of scientific notation on both axes
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter(useOffset=False))
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter(useOffset=False))
    ax.ticklabel_format(style="plain", axis="both")
    if show_grid:
        ax.grid(True, which="major", alpha=0.2, linestyle="-", linewidth=0.5, zorder=0)
        ax.grid(True, which="minor", alpha=0.1, linestyle=":", linewidth=0.3, zorder=0)


def plot_lightcurve_band(
    ax,
    mjd,
    values,
    errors,
    band,
    count=None,
    extra_label="",
    **kwargs,
):
    """Plot one band's lightcurve data with consistent publication styling.

    Parameters
    ----------
    ax : `matplotlib.axes.Axes`
        The axes to plot on.
    mjd : array-like
        X-axis values (Modified Julian Date).
    values : array-like
        Y-axis values (magnitude or flux).
    errors : array-like
        Y-axis error bars.
    band : `str`
        Band name for styling lookup.
    count : `int`, optional
        Number of data points (shown in legend as ``N=count``).
    extra_label : `str`, optional
        Extra text appended to the legend label.
    **kwargs
        Additional keyword arguments passed to ``ax.errorbar()``.
    """
    style = get_band_style(band)
    label = style["label"]
    if count is not None:
        label += f" (N={count})"
    if extra_label:
        label += f" {extra_label}"

    plot_kwargs = dict(
        fmt=style["marker"],
        color=style["color"],
        label=label,
        markersize=7,
        capsize=3,
        elinewidth=1.2,
        capthick=1.0,
        alpha=0.85,
        zorder=style["zorder"],
        markeredgecolor="black",
        markeredgewidth=0.4,
    )
    plot_kwargs.update(kwargs)

    ax.errorbar(mjd, values, yerr=errors, **plot_kwargs)


def set_title(ax, target_name, subtitle="", band=None):
    """Set a publication-quality title on the axes.

    Parameters
    ----------
    ax : `matplotlib.axes.Axes`
        The axes.
    target_name : `str`
        Primary title text (e.g. object name).
    subtitle : `str`, optional
        Secondary line below the title.
    band : `str`, optional
        Band name to append in parentheses.
    """
    title = target_name
    if band:
        title += f" ({band.upper()})"
    if subtitle:
        title += f"\n{subtitle}"
    ax.set_title(title, pad=10)
