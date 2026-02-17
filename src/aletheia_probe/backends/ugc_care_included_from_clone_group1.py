# SPDX-License-Identifier: MIT
"""UGC-CARE included (Group I clone-page left side) backend."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.ugc_care import UgcCareIncludedFromCloneGroup1Source
from .base import ConfiguredCachedBackend, get_backend_registry


class UgcCareIncludedFromCloneGroup1Backend(ConfiguredCachedBackend):
    """Backend for included journals listed on Group-I clone correction page."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="ugc_care_included_from_clone_group1",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: UgcCareIncludedFromCloneGroup1Source(),
        )


get_backend_registry().register_factory(
    "ugc_care_included_from_clone_group1",
    lambda: UgcCareIncludedFromCloneGroup1Backend(),
    default_config={},
)
