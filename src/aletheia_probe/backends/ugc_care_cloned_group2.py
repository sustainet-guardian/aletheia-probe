# SPDX-License-Identifier: MIT
"""UGC-CARE Group-II cloned journals backend."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.ugc_care import UgcCareClonedGroup2Source


class UgcCareClonedGroup2Backend(CachedBackend):
    """Backend for UGC-CARE Group-II cloned journals list."""

    def __init__(self) -> None:
        super().__init__(
            source_name="ugc_care_cloned_group2",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: UgcCareClonedGroup2Source | None = None

    def get_name(self) -> str:
        return "ugc_care_cloned_group2"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            from ..updater.sources.ugc_care import UgcCareClonedGroup2Source

            self._data_source = UgcCareClonedGroup2Source()
        return self._data_source


get_backend_registry().register_factory(
    "ugc_care_cloned_group2",
    lambda: UgcCareClonedGroup2Backend(),
    default_config={},
)
