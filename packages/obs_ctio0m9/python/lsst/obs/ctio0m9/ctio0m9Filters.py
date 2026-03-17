"""Filter definitions for the CTIO/SMARTS 0.9m telescope."""

from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

__all__ = ["CTIO0M9_FILTER_DEFINITIONS"]

CTIO0M9_FILTER_DEFINITIONS = FilterDefinitionCollection(
    # Johnson-Cousins broadband
    FilterDefinition("U", band="u", doc="Johnson U"),
    FilterDefinition("B", band="b", doc="Johnson B"),
    FilterDefinition("V", band="v", doc="Johnson V"),
    FilterDefinition("R", band="r", doc="Cousins R"),
    FilterDefinition("I", band="i", doc="Cousins I"),
    # Open/clear for calibrations
    FilterDefinition("OPEN", band=None, doc="Open filter wheel position"),
    # Calibration blocking filter (blocks light for bias/dark)
    FilterDefinition("CB", band=None, doc="Calibration blocking filter"),
    # Dichroic filter variants found in archive
    FilterDefinition("DIA", band=None, doc="Dichroic filter"),
    # Combination filters from dual wheel (sorted alphabetically)
    # CB (calibration blocking) combinations
    FilterDefinition("CB+B", band="b", doc="CB + Johnson B"),
    FilterDefinition("CB+V", band="v", doc="CB + Johnson V"),
    FilterDefinition("CB+R", band="r", doc="CB + Cousins R"),
    FilterDefinition("CB+I", band="i", doc="CB + Cousins I"),
    # DIA (dichroic) combinations
    FilterDefinition("B+DIA", band="b", doc="Johnson B + Dichroic"),
    FilterDefinition("DIA+U", band="u", doc="Dichroic + Johnson U"),
    FilterDefinition("DIA+V", band="v", doc="Dichroic + Johnson V"),
    FilterDefinition("DIA+R", band="r", doc="Dichroic + Cousins R"),
    FilterDefinition("DIA+I", band="i", doc="Dichroic + Cousins I"),
    FilterDefinition("DIA+Y", band="y", doc="Dichroic + Y-band"),
)
