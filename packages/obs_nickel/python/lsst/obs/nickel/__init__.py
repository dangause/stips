from ._version import __version__
from .profile import profile
from .translator import NickelTranslator

__all__ = ["NickelTranslator", "profile", "__version__"]

try:
    from ._instrument import Nickel
    from .rawFormatter import NickelRawFormatter  # noqa: F401

    __all__ += ["Nickel", "NickelRawFormatter"]
except ImportError:
    pass

try:
    from . import calibCombine, visitInfo  # noqa: F401

    __all__ += ["calibCombine", "visitInfo"]
except ImportError:
    pass
