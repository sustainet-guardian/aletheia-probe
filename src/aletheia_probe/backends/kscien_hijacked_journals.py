# SPDX-License-Identifier: MIT
"""Kscien hijacked journals backend for predatory journal assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.kscien_hijacked_journals import KscienHijackedJournalsSource
from .base import ConfiguredCachedBackend, get_backend_registry


class KscienHijackedJournalsBackend(ConfiguredCachedBackend):
    """Backend that checks against Kscien's hijacked journals list."""

    def __init__(self) -> None:
        """Initialize the Kscien hijacked journals backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            backend_name="kscien_hijacked_journals",
            list_type=AssessmentType.HIJACKED,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
            data_source_factory=lambda: KscienHijackedJournalsSource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_hijacked_journals",
    lambda: KscienHijackedJournalsBackend(),
    default_config={},
)
