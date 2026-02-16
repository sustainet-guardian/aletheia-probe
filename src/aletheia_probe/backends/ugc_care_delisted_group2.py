# SPDX-License-Identifier: MIT
"""UGC-CARE Group-II delisted journals backend."""

from ..enums import AssessmentType, EvidenceType
from ..updater.core import DataSource
from ..updater.sources.ugc_care import UgcCareDelistedGroup2Source
from .base import CachedBackend, get_backend_registry


class UgcCareDelistedGroup2Backend(CachedBackend):
    """Backend for UGC-CARE Group-II delisted journals."""

    def __init__(self) -> None:
        super().__init__(
            source_name="ugc_care_delisted_group2",
            list_type=AssessmentType.PREDATORY,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: UgcCareDelistedGroup2Source | None = None

    def get_name(self) -> str:
        return "ugc_care_delisted_group2"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.PREDATORY_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            self._data_source = UgcCareDelistedGroup2Source()
        return self._data_source


get_backend_registry().register_factory(
    "ugc_care_delisted_group2",
    lambda: UgcCareDelistedGroup2Backend(),
    default_config={},
)
