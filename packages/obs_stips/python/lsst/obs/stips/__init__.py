import logging

from .translator import StipsTranslator

__all__ = ["StipsTranslator"]

_LOG = logging.getLogger(__name__)

# Import roots that are legitimately absent outside the LSST stack (or the
# optional plotting extra). An ImportError rooted here means the corresponding
# optional feature is simply unavailable and is swallowed; ANY other ImportError
# (a typo'd intra-package import, or a genuinely-missing hard dependency such as
# numpy/pyyaml) is re-raised so it cannot silently delete a whole subpackage.
_OPTIONAL_IMPORT_ROOTS = ("lsst", "matplotlib")


def _is_optional_missing(exc: ImportError) -> bool:
    name = getattr(exc, "name", None) or ""
    # A broken import of our OWN package (e.g. a typo'd relative import) reports
    # a name under lsst.obs.stips.*; that is a real bug, never an optional
    # feature, so it must re-raise rather than be swallowed as "lsst-rooted".
    if name == "lsst.obs.stips" or name.startswith("lsst.obs.stips."):
        return False
    root = name.split(".", 1)[0]
    return root in _OPTIONAL_IMPORT_ROOTS


try:
    from .formatter import StipsRawFormatter  # noqa: F401
    from .instrument import StipsInstrument  # noqa: F401

    __all__ += ["StipsInstrument", "StipsRawFormatter"]
except ImportError as exc:
    if not _is_optional_missing(exc):
        raise
    _LOG.debug(
        "obs_stips: instrument/formatter disabled (optional import missing: %s)",
        exc.name,
    )

try:
    from . import plotting, tasks  # noqa: F401

    __all__ += ["plotting", "tasks"]
except ImportError as exc:
    if not _is_optional_missing(exc):
        raise
    _LOG.debug(
        "obs_stips: plotting/tasks disabled (optional import missing: %s)",
        exc.name,
    )
