# SPDX-License-Identifier: MIT
"""Beall's List backend for predatory journal assessment."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.bealls import BeallsListSource
from .base import ConfiguredCachedBackend, get_backend_registry


class BeallsListBackend(ConfiguredCachedBackend):
    """Backend that checks against Beall's list of predatory journals."""

    def __init__(self) -> None:
        """Initialize the Beall's List backend.

        Sets up cache with 7-day TTL (24 * 7 hours) as Beall's list is static/archived.
        """
        super().__init__(
            backend_name="bealls",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 7,  # Weekly cache for static lists
            data_source_factory=lambda: BeallsListSource(),
        )


# Register the backend factory
get_backend_registry().register_factory(
    "bealls", lambda: BeallsListBackend(), default_config={}
)
