# SPDX-License-Identifier: MIT
"""DBLP conference backend for legitimate conference verification."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.dblp import DblpVenueSource
from .base import ConfiguredCachedBackend, get_backend_registry


_CACHE_TTL_HOURS = 24 * 30  # Monthly cache for large DBLP dump refreshes


class DblpVenuesBackend(ConfiguredCachedBackend):
    """Backend that checks venue legitimacy using DBLP venue series data."""

    def __init__(self) -> None:
        """Initialize DBLP venues backend."""
        super().__init__(
            backend_name="dblp_venues",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=_CACHE_TTL_HOURS,
            data_source_factory=lambda: DblpVenueSource(),
        )


get_backend_registry().register_factory(
    "dblp_venues",
    lambda: DblpVenuesBackend(),
    default_config={},
)
