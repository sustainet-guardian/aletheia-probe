# SPDX-License-Identifier: MIT
"""Kscien standalone journals backend for predatory journal assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.kscien_standalone_journals import (
        KscienStandaloneJournalsSource,
    )


class KscienStandaloneJournalsBackend(CachedBackend):
    """Backend that checks against Kscien's standalone predatory journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien standalone journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_standalone_journals",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )
        self._data_source: KscienStandaloneJournalsSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier."""
        return "kscien_standalone_journals"

    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides.

        Returns:
            EvidenceType.PREDATORY_LIST as this is a predatory journal list.
        """
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the KscienStandaloneJournalsSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.kscien_standalone_journals import (
                KscienStandaloneJournalsSource,
            )

            self._data_source = KscienStandaloneJournalsSource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_standalone_journals",
    lambda: KscienStandaloneJournalsBackend(),
    default_config={},
)
