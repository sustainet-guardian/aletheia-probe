# SPDX-License-Identifier: MIT
"""Kscien standalone journals backend for predatory journal assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.kscien_standalone_journals import (
    KscienStandaloneJournalsSource,
)
from .base import ConfiguredCachedBackend, get_backend_registry


class KscienStandaloneJournalsBackend(ConfiguredCachedBackend):
    """Backend that checks against Kscien's standalone predatory journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien standalone journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            backend_name="kscien_standalone_journals",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
            data_source_factory=lambda: KscienStandaloneJournalsSource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_standalone_journals",
    lambda: KscienStandaloneJournalsBackend(),
    default_config={},
)
