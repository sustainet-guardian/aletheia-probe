# SPDX-License-Identifier: MIT
"""Scopus backend for legitimate journal verification."""

from .base import CachedBackend, get_backend_registry


class ScopusBackend(CachedBackend):
    """Backend that checks against Scopus journal list for legitimate journals.

    This backend is optional and only active if the user has downloaded
    and placed a Scopus journal list Excel file in ~/.aletheia-probe/scopus/
    """

    def __init__(self) -> None:
        """Initialize the Scopus backend.

        Sets up cache with 30-day TTL as Scopus data is user-provided and static.
        Requires user to manually download and place Scopus journal list.
        """
        super().__init__(
            source_name="scopus",
            list_type="legitimate",
            cache_ttl_hours=24 * 30,  # Monthly cache for static file
        )

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "scopus"

    def get_description(self) -> str:
        """Return a human-readable description of the backend.

        Returns:
            Description string for display purposes
        """
        return "Checks against Scopus indexed journals for legitimate journals"


# Register the backend factory
get_backend_registry().register_factory(
    "scopus", lambda: ScopusBackend(), default_config={}
)
