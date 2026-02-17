# SPDX-License-Identifier: MIT
"""UGC-CARE included (Group II clone-page left side) backend."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.ugc_care import UgcCareIncludedFromCloneGroup2Source
from .base import ConfiguredCachedBackend, get_backend_registry


class UgcCareIncludedFromCloneGroup2Backend(ConfiguredCachedBackend):
    """Backend for included journals listed on Group-II clone correction page."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="ugc_care_included_from_clone_group2",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: UgcCareIncludedFromCloneGroup2Source(),
        )


get_backend_registry().register_factory(
    "ugc_care_included_from_clone_group2",
    lambda: UgcCareIncludedFromCloneGroup2Backend(),
    default_config={},
)
