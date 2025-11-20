# SPDX-License-Identifier: MIT
"""Kscien standalone journals backend for predatory journal assessment."""

from .base import CachedBackend, get_backend_registry


class KscienStandaloneJournalsBackend(CachedBackend):
    """Backend that checks against Kscien's standalone predatory journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien standalone journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_standalone_journals",
            list_type="predatory",
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )

    def get_name(self) -> str:
        """Return the backend identifier."""
        return "kscien_standalone_journals"

    def get_description(self) -> str:
        """Return a human-readable description of the backend."""
        return "Checks against Kscien's list of standalone predatory journals (1476+ entries)"


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_standalone_journals",
    lambda: KscienStandaloneJournalsBackend(),
    default_config={},
)
