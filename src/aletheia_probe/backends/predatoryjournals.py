# SPDX-License-Identifier: MIT
"""Predatory Journals database backend for journal assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.predatoryjournals import PredatoryJournalsSource


# Monthly cache for community-maintained lists (30 days)
_CACHE_TTL_HOURS = 24 * 30


class PredatoryJournalsBackend(CachedBackend):
    """Backend that checks against predatoryjournals.org lists.

    Queries both the predatory journals list and the predatory publishers list
    from predatoryjournals.org to identify predatory publications.
    """

    def __init__(self) -> None:
        """Initialize the Predatory Journals backend.

        Sets up cache with 30-day TTL as the list is updated monthly.
        """
        super().__init__(
            source_name="predatoryjournals",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=_CACHE_TTL_HOURS,
        )
        self._data_source: PredatoryJournalsSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "predatoryjournals"

    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides.

        Returns:
            EvidenceType.PREDATORY_LIST as this is a predatory journal list.
        """
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the PredatoryJournalsSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.predatoryjournals import PredatoryJournalsSource

            self._data_source = PredatoryJournalsSource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "predatoryjournals", lambda: PredatoryJournalsBackend(), default_config={}
)
