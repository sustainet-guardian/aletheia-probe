# SPDX-License-Identifier: MIT
"""DBLP conference backend for legitimate conference verification."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.dblp import DblpVenueSource


_CACHE_TTL_HOURS = 24 * 30  # Monthly cache for large DBLP dump refreshes


class DblpVenuesBackend(CachedBackend):
    """Backend that checks venue legitimacy using DBLP venue series data."""

    def __init__(self) -> None:
        """Initialize DBLP venues backend."""
        super().__init__(
            source_name="dblp_venues",
            list_type=AssessmentType.LEGITIMATE,
            cache_ttl_hours=_CACHE_TTL_HOURS,
        )
        self._data_source: DblpVenueSource | None = None

    def get_name(self) -> str:
        """Return backend identifier."""
        return "dblp_venues"

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type for DBLP venues backend."""
        return EvidenceType.LEGITIMATE_LIST

    def get_data_source(self) -> "DataSource | None":
        """Get DBLP venue source for cache synchronization."""
        if self._data_source is None:
            from ..updater.sources.dblp import DblpVenueSource

            self._data_source = DblpVenueSource()
        return self._data_source


get_backend_registry().register_factory(
    "dblp_venues",
    lambda: DblpVenuesBackend(),
    default_config={},
)
