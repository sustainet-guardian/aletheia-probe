# SPDX-License-Identifier: MIT
"""Kscien publishers backend for predatory journal assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.kscien_publishers import KscienPublishersSource
from .base import ConfiguredCachedBackend, get_backend_registry


class KscienPublishersBackend(ConfiguredCachedBackend):
    """Backend that checks against Kscien's predatory publishers list."""

    def __init__(self) -> None:
        """Initialize the Kscien publishers backend.

        Sets up cache with 7-day TTL as Kscien list is updated weekly.
        """
        super().__init__(
            backend_name="kscien_publishers",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 7,  # Weekly cache for curated lists
            data_source_factory=lambda: KscienPublishersSource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "kscien_publishers", KscienPublishersBackend, default_config={}
)
