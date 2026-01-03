# SPDX-License-Identifier: MIT
"""Kscien hijacked journals backend for predatory journal assessment."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.kscien_hijacked_journals import KscienHijackedJournalsSource


class KscienHijackedJournalsBackend(CachedBackend):
    """Backend that checks against Kscien's hijacked journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien hijacked journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            source_name="kscien_hijacked_journals",
            list_type=AssessmentType.HIJACKED,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
        )
        self._data_source: KscienHijackedJournalsSource | None = None

    def get_name(self) -> str:
        """Return the backend identifier."""
        return "kscien_hijacked_journals"

    def get_evidence_type(self) -> EvidenceType:
        """Return the evidence type for this backend."""
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get the KscienHijackedJournalsSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.kscien_hijacked_journals import (
                KscienHijackedJournalsSource,
            )

            self._data_source = KscienHijackedJournalsSource()
        return self._data_source


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_hijacked_journals",
    lambda: KscienHijackedJournalsBackend(),
    default_config={},
)
