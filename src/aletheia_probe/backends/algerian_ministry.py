# SPDX-License-Identifier: MIT
"""Algerian Ministry backend for predatory journal verification."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.algerian import AlgerianMinistrySource


class AlgerianMinistryBackend(CachedBackend):
    """Backend that checks Algerian Ministry of Higher Education predatory journal list."""

    def __init__(self) -> None:
        """Initialize the Algerian Ministry backend.

        Sets up cache with 48-hour TTL due to less frequent updates from source.
        """
        super().__init__(
            source_name="algerian_ministry",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=48,  # Cache for 48 hours due to less frequent updates
        )
        self._data_source: AlgerianMinistrySource | None = None

    def get_evidence_type(self) -> EvidenceType:
        """Return the evidence type for this backend.

        Returns:
            EvidenceType.PREDATORY_LIST
        """
        return EvidenceType.PREDATORY_LIST

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "algerian_ministry"

    def get_data_source(self) -> "DataSource | None":
        """Get the AlgerianMinistrySource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.algerian import AlgerianMinistrySource

            self._data_source = AlgerianMinistrySource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "algerian_ministry", lambda: AlgerianMinistryBackend(), default_config={}
)
