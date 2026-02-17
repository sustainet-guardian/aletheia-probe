# SPDX-License-Identifier: MIT
"""Kscien Predatory Conferences backend for conference assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.kscien_generic import KscienGenericSource
from ..updater.sources.kscien_helpers import PublicationType
from .base import ConfiguredCachedBackend, get_backend_registry


class KscienPredatoryConferencesBackend(ConfiguredCachedBackend):
    """Backend that checks against Kscien predatory conference lists."""

    def __init__(self) -> None:
        """Initialize the Kscien Predatory Conferences backend.

        Sets up cache with 7-day TTL as predatory conference lists are relatively static.
        """
        super().__init__(
            backend_name="kscien_predatory_conferences",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 7,  # Weekly cache for conference lists
            data_source_factory=lambda: KscienGenericSource(
                publication_type=PublicationType.PREDATORY_CONFERENCES
            ),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_predatory_conferences",
    lambda: KscienPredatoryConferencesBackend(),
    default_config={},
)
