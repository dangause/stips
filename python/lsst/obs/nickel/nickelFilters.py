from lsst.obs.base import FilterDefinition, FilterDefinitionCollection

NICKEL_FILTER_DEFINITIONS = FilterDefinitionCollection(
    FilterDefinition(
        physical_filter="B",
        band="b",
        doc="Johnson/Bessell B",
    ),
    FilterDefinition(
        physical_filter="V",
        band="v",
        doc="Johnson/Bessell V",
    ),
    FilterDefinition(
        physical_filter="R",
        band="r",
        doc="Cousins R",
    ),
    FilterDefinition(
        physical_filter="I",
        band="i",
        doc="Cousins I",
    ),
)
