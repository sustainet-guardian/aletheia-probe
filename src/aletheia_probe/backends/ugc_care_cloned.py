# SPDX-License-Identifier: MIT
"""UGC-CARE cloned journals backend."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.ugc_care import UgcCareClonedSource


class UgcCareClonedBackend(CachedBackend):
    """Backend for UGC-CARE Group-I cloned journals list."""

    def __init__(self) -> None:
        super().__init__(
            source_name="ugc_care_cloned",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: UgcCareClonedSource | None = None

    def get_name(self) -> str:
        return "ugc_care_cloned"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            from ..updater.sources.ugc_care import UgcCareClonedSource

            self._data_source = UgcCareClonedSource()
        return self._data_source


get_backend_registry().register_factory(
    "ugc_care_cloned", lambda: UgcCareClonedBackend(), default_config={}
)
