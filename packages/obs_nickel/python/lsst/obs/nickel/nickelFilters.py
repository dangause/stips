from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

NICKEL_FILTER_DEFINITIONS = FilterDefinitionCollection(
    FilterDefinition("B", band="b", doc="Johnson/Bessell B"),
    FilterDefinition("V", band="v", doc="Johnson/Bessell V"),
    FilterDefinition("R", band="r", doc="Cousins R"),
    FilterDefinition("I", band="i", doc="Cousins I"),
    FilterDefinition("clear", band=None, doc="Unfiltered / open wheel"),
)
