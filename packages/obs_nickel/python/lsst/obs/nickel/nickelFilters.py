from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

NICKEL_FILTER_DEFINITIONS = FilterDefinitionCollection(
    # Standard broadband
    FilterDefinition("B", band="b", doc="Johnson/Bessell B"),
    FilterDefinition("V", band="v", doc="Johnson/Bessell V"),
    FilterDefinition("R", band="r", doc="Cousins R"),
    FilterDefinition("I", band="i", doc="Cousins I"),
    FilterDefinition("clear", band=None, doc="Unfiltered / open wheel"),
    # Sloan-like
    FilterDefinition("gp", band="gp", doc="Sloan g-prime"),
    FilterDefinition("rp", band="rp", doc="Sloan r-prime"),
    # Narrowband
    FilterDefinition("Halpha", band="halpha", doc="H-alpha 6563A narrowband"),
    FilterDefinition("OIII", band="oiii", doc="[OIII] 5007A narrowband"),
)
