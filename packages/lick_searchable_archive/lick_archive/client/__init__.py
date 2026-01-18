"""
Client modules for accessing the Lick Archive API.

This module provides client classes for querying and ingesting data
into the Lick Observatory Searchable Archive.
"""

from lick_archive.client.lick_archive_client import (
    LickArchiveClient,
    QueryTerm,
)
from lick_archive.client.lick_archive_ingest_client import (
    LickArchiveIngestClient,
)

__all__ = [
    "LickArchiveClient",
    "LickArchiveIngestClient",
    "QueryTerm",
]
