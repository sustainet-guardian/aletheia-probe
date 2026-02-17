# SPDX-License-Identifier: MIT
"""UGC-CARE Group-II delisted journals backend."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.ugc_care import UgcCareDelistedGroup2Source
from .base import ConfiguredCachedBackend, get_backend_registry


class UgcCareDelistedGroup2Backend(ConfiguredCachedBackend):
    """Backend for UGC-CARE Group-II delisted journals."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="ugc_care_delisted_group2",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: UgcCareDelistedGroup2Source(),
        )


get_backend_registry().register_factory(
    "ugc_care_delisted_group2",
    lambda: UgcCareDelistedGroup2Backend(),
    default_config={},
)
