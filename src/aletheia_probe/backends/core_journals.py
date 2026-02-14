# SPDX-License-Identifier: MIT
"""CORE journal rankings backend for legitimate journal verification."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.core import CoreJournalSource


class CoreJournalsBackend(CachedBackend):
    """Backend that checks journals against CORE ranked journals."""

    def __init__(self) -> None:
        super().__init__(
            source_name="core_journals",
            list_type=AssessmentType.LEGITIMATE,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: CoreJournalSource | None = None

    def get_name(self) -> str:
        return "core_journals"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.LEGITIMATE_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            from ..updater.sources.core import CoreJournalSource

            self._data_source = CoreJournalSource()
        return self._data_source


get_backend_registry().register_factory(
    "core_journals",
    lambda: CoreJournalsBackend(),
    default_config={},
)
