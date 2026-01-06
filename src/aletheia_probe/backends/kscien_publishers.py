# SPDX-License-Identifier: MIT
"""Kscien publishers backend for predatory journal assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.kscien_publishers import KscienPublishersSource


class KscienPublishersBackend(CachedBackend):
    """Backend that checks against Kscien's predatory publishers list."""

    def __init__(self) -> None:
        """Initialize the Kscien publishers backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_publishers",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )
        self._data_source: KscienPublishersSource | None = None

    def get_name(self) -> str:
        """Get the unique identifier for this backend.

        Returns:
            str: The backend identifier string "kscien_publishers".
        """
        return "kscien_publishers"

    def get_evidence_type(self) -> EvidenceType:
        """Return the evidence type for this backend."""
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the KscienPublishersSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.kscien_publishers import KscienPublishersSource

            self._data_source = KscienPublishersSource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_publishers", KscienPublishersBackend, default_config={}
)
