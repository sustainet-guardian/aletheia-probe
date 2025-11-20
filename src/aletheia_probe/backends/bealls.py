# SPDX-License-Identifier: MIT
"""Beall's List backend for predatory journal assessment."""

from .base import CachedBackend, get_backend_registry


class BeallsListBackend(CachedBackend):
    """Backend that checks against Beall's list of predatory journals."""

    def __init__(self) -> None:
        """Initialize the Beall's List backend.

        Sets up cache with 7-day TTL as Beall's list is static/archived.
        """
        super().__init__(
            source_name="bealls",
            list_type="predatory",
            cache_ttl_hours=24 * 7,  # Weekly cache for static lists
        )

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "bealls"

    def get_description(self) -> str:
        """Return a human-readable description of the backend.

        Returns:
            Description string for display purposes
        """
        return (
            "Checks against Beall's archived list of predatory journals and publishers"
        )


# Register the backend factory
get_backend_registry().register_factory(
    "bealls", lambda: BeallsListBackend(), default_config={}
)
