# SPDX-License-Identifier: MIT
"""Algerian Ministry backend for predatory journal verification."""

from ..enums import AssessmentType
from .base import CachedBackend, get_backend_registry


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

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "algerian_ministry"


# Register the backend factory
get_backend_registry().register_factory(
    "algerian_ministry", lambda: AlgerianMinistryBackend(), default_config={}
)
