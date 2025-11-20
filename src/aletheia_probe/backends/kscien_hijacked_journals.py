# SPDX-License-Identifier: MIT
"""Kscien hijacked journals backend for predatory journal assessment."""

from .base import CachedBackend, get_backend_registry


class KscienHijackedJournalsBackend(CachedBackend):
    """Backend that checks against Kscien's hijacked journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien hijacked journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_hijacked_journals",
            list_type="hijacked",  # Different assessment type for hijacked journals
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )

    def get_name(self) -> str:
        """Return the backend identifier."""
        return "kscien_hijacked_journals"

    def get_description(self) -> str:
        """Return a human-readable description of the backend."""
        return "Checks against Kscien's list of hijacked journals (234+ entries)"


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_hijacked_journals",
    lambda: KscienHijackedJournalsBackend(),
    default_config={},
)
