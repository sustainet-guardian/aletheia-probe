# SPDX-License-Identifier: MIT
"""UGC-CARE included (Group I clone-page left side) backend."""

from typing import TYPE_CHECKING

from ..enums import AssessmentType, EvidenceType
from .base import CachedBackend, get_backend_registry


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.ugc_care import UgcCareIncludedFromCloneGroup1Source


class UgcCareIncludedFromCloneGroup1Backend(CachedBackend):
    """Backend for included journals listed on Group-I clone correction page."""

    def __init__(self) -> None:
        super().__init__(
            source_name="ugc_care_included_from_clone_group1",
            list_type=AssessmentType.LEGITIMATE,
            cache_ttl_hours=24 * 30,
        )
        self._data_source: UgcCareIncludedFromCloneGroup1Source | None = None

    def get_name(self) -> str:
        return "ugc_care_included_from_clone_group1"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.LEGITIMATE_LIST

    def get_data_source(self) -> "DataSource | None":
        if self._data_source is None:
            from ..updater.sources.ugc_care import UgcCareIncludedFromCloneGroup1Source

            self._data_source = UgcCareIncludedFromCloneGroup1Source()
        return self._data_source


get_backend_registry().register_factory(
    "ugc_care_included_from_clone_group1",
    lambda: UgcCareIncludedFromCloneGroup1Backend(),
    default_config={},
)
