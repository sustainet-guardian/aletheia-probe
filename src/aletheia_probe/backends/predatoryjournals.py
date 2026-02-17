# SPDX-License-Identifier: MIT
"""Predatory Journals database backend for journal assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.predatoryjournals import PredatoryJournalsSource
from .base import ConfiguredCachedBackend, get_backend_registry


# Monthly cache for community-maintained lists (30 days)
_CACHE_TTL_HOURS = 24 * 30


class PredatoryJournalsBackend(ConfiguredCachedBackend):
    """Backend that checks against predatoryjournals.org lists.

    Queries both the predatory journals list and the predatory publishers list
    from predatoryjournals.org to identify predatory publications.
    """

    def __init__(self) -> None:
        """Initialize the Predatory Journals backend.

        Sets up cache with 30-day TTL as the list is updated monthly.
        """
        super().__init__(
            backend_name="predatoryjournals",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=_CACHE_TTL_HOURS,
            data_source_factory=lambda: PredatoryJournalsSource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "predatoryjournals", lambda: PredatoryJournalsBackend(), default_config={}
)
