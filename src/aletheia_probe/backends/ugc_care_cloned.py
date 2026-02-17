# SPDX-License-Identifier: MIT
"""UGC-CARE cloned journals backend."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.ugc_care import UgcCareClonedSource
from .base import ConfiguredCachedBackend, get_backend_registry


class UgcCareClonedBackend(ConfiguredCachedBackend):
    """Backend for UGC-CARE Group-I cloned journals list."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="ugc_care_cloned",
            list_type=AssessmentType.PREDATORY,
            evidence_type=EvidenceType.PREDATORY_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: UgcCareClonedSource(),
        )


get_backend_registry().register_factory(
    "ugc_care_cloned", lambda: UgcCareClonedBackend(), default_config={}
)
