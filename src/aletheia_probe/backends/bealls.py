# SPDX-License-Identifier: MIT
"""Beall's List backend for predatory journal assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.bealls import BeallsListSource


class BeallsListBackend(CachedBackend):
    """Backend that checks against Beall's list of predatory journals."""

    def __init__(self) -> None:
        """Initialize the Beall's List backend.

        Sets up cache with 7-day TTL (24 * 7 hours) as Beall's list is static/archived.
        """
        super().__init__(
            source_name="bealls",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 7,  # Weekly cache for static lists
        )
        self._data_source: BeallsListSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier.

        Returns:
            Backend name string
        """
        return "bealls"

    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides.

        Returns:
            EvidenceType.PREDATORY_LIST as this is a predatory journal list.
        """
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the BeallsListSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.bealls import BeallsListSource

            self._data_source = BeallsListSource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "bealls", lambda: BeallsListBackend(), default_config={}
)
