# SPDX-License-Identifier: MIT
"""CORE/ICORE conference rankings backend for legitimate conference verification."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.core import CoreConferenceSource
from .base import ConfiguredCachedBackend, get_backend_registry


class CoreConferencesBackend(ConfiguredCachedBackend):
    """Backend that checks conferences against CORE/ICORE ranked venues."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="core_conferences",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: CoreConferenceSource(),
        )


get_backend_registry().register_factory(
    "core_conferences",
    lambda: CoreConferencesBackend(),
    default_config={},
)
