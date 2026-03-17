"""Filter definitions for the CTIO/SMARTS 0.9m telescope."""

from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

__all__ = ["CTIO0M9_FILTER_DEFINITIONS"]

CTIO0M9_FILTER_DEFINITIONS = FilterDefinitionCollection(
    # Johnson-Cousins broadband (with lambdaEff for photometry)
    FilterDefinition(physical_filter="U", band="u", lambdaEff=357.0, alias={"u"}),
    FilterDefinition(physical_filter="B", band="b", lambdaEff=420.2, alias={"b"}),
    FilterDefinition(physical_filter="V", band="v", lambdaEff=547.5, alias={"v"}),
    FilterDefinition(physical_filter="R", band="r", lambdaEff=640.0, alias={"r"}),
    FilterDefinition(physical_filter="I", band="i", lambdaEff=811.8, alias={"i"}),
    # Open/clear for calibrations
    FilterDefinition(
        physical_filter="OPEN", band=None, doc="Open filter wheel position"
    ),
    # Calibration blocking filter (blocks light for bias/dark)
    FilterDefinition(
        physical_filter="CB", band=None, doc="Calibration blocking filter"
    ),
    # Dichroic filter variants found in archive
    FilterDefinition(physical_filter="DIA", band=None, doc="Dichroic filter"),
    # Combination filters from dual wheel (sorted alphabetically)
    # CB (calibration blocking) combinations
    FilterDefinition(physical_filter="CB+B", band="b", lambdaEff=420.2),
    FilterDefinition(physical_filter="CB+V", band="v", lambdaEff=547.5),
    FilterDefinition(physical_filter="CB+R", band="r", lambdaEff=640.0),
    FilterDefinition(physical_filter="CB+I", band="i", lambdaEff=811.8),
    # DIA (dichroic) combinations
    FilterDefinition(physical_filter="B+DIA", band="b", lambdaEff=420.2),
    FilterDefinition(physical_filter="DIA+U", band="u", lambdaEff=357.0),
    FilterDefinition(physical_filter="DIA+V", band="v", lambdaEff=547.5),
    FilterDefinition(physical_filter="DIA+R", band="r", lambdaEff=640.0),
    FilterDefinition(physical_filter="DIA+I", band="i", lambdaEff=811.8),
    FilterDefinition(physical_filter="DIA+Y", band="y", lambdaEff=1020.0),  # Y-band
)
