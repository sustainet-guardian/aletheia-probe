# SPDX-License-Identifier: MIT
"""CORE/ICORE conference rankings backend for legitimate conference verification."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.core import CoreConferenceSource


class CoreConferencesBackend(CachedBackend):
    """Backend that checks conferences against CORE/ICORE ranked venues."""

    def __init__(self) -> None:
        super().__init__(
            source_name="core_conferences",
            list_type=AssessmentType.LEGITIMATE,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: CoreConferenceSource | None = None

    def get_name(self) -> str:
        return "core_conferences"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.LEGITIMATE_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            from ..updater.sources.core import CoreConferenceSource

            self._data_source = CoreConferenceSource()
        return self._data_source


get_backend_registry().register_factory(
    "core_conferences",
    lambda: CoreConferencesBackend(),
    default_config={},
)
