# SPDX-License-Identifier: MIT
"""CORE journal rankings backend for legitimate journal verification."""

from ..enums import AssessmentType, EvidenceType
from ..updater.sources.core import CoreJournalSource
from .base import ConfiguredCachedBackend, get_backend_registry


class CoreJournalsBackend(ConfiguredCachedBackend):
    """Backend that checks journals against CORE ranked journals."""

    def __init__(self) -> None:
        super().__init__(
            backend_name="core_journals",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: CoreJournalSource(),
        )


get_backend_registry().register_factory(
    "core_journals",
    lambda: CoreJournalsBackend(),
    default_config={},
)
