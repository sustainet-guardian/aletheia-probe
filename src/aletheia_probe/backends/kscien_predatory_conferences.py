# SPDX-License-Identifier: MIT
"""Kscien Predatory Conferences backend for conference assessment."""

from ..enums import AssessmentType
from .base import CachedBackend, get_backend_registry


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

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "kscien_predatory_conferences"

    def get_description(self) -> str:
        """Return a human-readable description of the backend.

        Returns:
            Description string for display purposes
        """
        return "Checks against Kscien predatory conference lists"


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_predatory_conferences",
    lambda: KscienPredatoryConferencesBackend(),
    default_config={},
)
