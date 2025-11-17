"""Kscien publishers backend for predatory journal assessment."""

from .base import CachedBackend, get_backend_registry


class KscienPublishersBackend(CachedBackend):
    """Backend that checks against Kscien's predatory publishers list."""

    def __init__(self) -> None:
        """Initialize the Kscien publishers backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_publishers",
            list_type="predatory",
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )

    def get_name(self) -> str:
        """Return the backend identifier."""
        return "kscien_publishers"

    def get_description(self) -> str:
        """Return a human-readable description of the backend."""
        return "Checks against Kscien's list of predatory publishers (1271+ entries)"


# Register the backend
get_backend_registry().register(KscienPublishersBackend())
