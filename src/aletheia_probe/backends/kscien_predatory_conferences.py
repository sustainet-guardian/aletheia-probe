# SPDX-License-Identifier: MIT
"""Kscien Predatory Conferences backend for conference assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.kscien_generic import KscienGenericSource


class KscienPredatoryConferencesBackend(CachedBackend):
    """Backend that checks against Kscien predatory conference lists."""

    def __init__(self) -> None:
        """Initialize the Kscien Predatory Conferences backend.

        Sets up cache with 7-day TTL as predatory conference lists are relatively static.
        """
        super().__init__(
            source_name="kscien_predatory_conferences",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 7,  # Weekly cache for conference lists
        )
        self._data_source: KscienGenericSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "kscien_predatory_conferences"

    def get_evidence_type(self) -> EvidenceType:
        """Return the evidence type for this backend."""
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the KscienGenericSource instance for predatory conferences data synchronization."""
        if self._data_source is None:
            from ..updater.sources.kscien_generic import KscienGenericSource
            from ..updater.sources.kscien_helpers import PublicationType

            self._data_source = KscienGenericSource(
                publication_type=PublicationType.PREDATORY_CONFERENCES
            )
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_predatory_conferences",
    lambda: KscienPredatoryConferencesBackend(),
    default_config={},
)
