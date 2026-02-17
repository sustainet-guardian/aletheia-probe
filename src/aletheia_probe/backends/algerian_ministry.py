# SPDX-License-Identifier: MIT
"""Algerian Ministry backend for predatory journal verification."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.algerian import AlgerianMinistrySource
from .base import ConfiguredCachedBackend, get_backend_registry


class AlgerianMinistryBackend(ConfiguredCachedBackend):
    """Backend that checks Algerian Ministry of Higher Education predatory journal list."""

    def __init__(self) -> None:
        """Initialize the Algerian Ministry backend.

        Sets up cache with 48-hour TTL due to less frequent updates from source.
        """
        super().__init__(
            backend_name="algerian_ministry",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=48,  # Cache for 48 hours due to less frequent updates
            data_source_factory=lambda: AlgerianMinistrySource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "algerian_ministry", lambda: AlgerianMinistryBackend(), default_config={}
)
