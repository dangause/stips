"""
Lick Observatory Searchable Archive

A package for accessing and managing data from the Lick Observatory archive.
"""

__version__ = "0.1.0"

# Import commonly used client classes for convenience
from lick_archive.client import (
    LickArchiveClient,
    LickArchiveIngestClient,
    QueryTerm,
)

__all__ = [
    "LickArchiveClient",
    "LickArchiveIngestClient",
    "QueryTerm",
    "__version__",
]
