# SPDX-License-Identifier: MIT
"""Predatory Journals database backend for journal assessment."""

from ..enums import AssessmentType
from .base import CachedBackend, get_backend_registry


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

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "predatoryjournals"

    def get_description(self) -> str:
        """Return a human-readable description of the backend.

        Returns:
            Description string for display purposes
        """
        return (
            "Checks against predatoryjournals.org curated lists of "
            "predatory journals and publishers"
        )


# Register the backend factory
get_backend_registry().register_factory(
    "predatoryjournals", lambda: PredatoryJournalsBackend(), default_config={}
)
