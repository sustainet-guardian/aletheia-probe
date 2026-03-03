# SPDX-License-Identifier: MIT
"""PubMed NLM backend for legitimate biomedical journal verification."""

from typing import Any

from ..enums import AssessmentType, EvidenceType
from ..models import QueryInput
from ..updater.sources.pubmed import PubMedNLMSource
from .base import ConfiguredCachedBackend, get_backend_registry


_CONFIDENCE_MEDLINE = 0.65
_CONFIDENCE_NLM_CATALOG = 0.50


class PubMedBackend(ConfiguredCachedBackend):
    """Backend that checks journals against the NLM/PubMed journal lists.

    Uses two NCBI data sources with differentiated confidence scores:

    - **MEDLINE subset** (``is_medline: True``): ``confidence = 0.65``
      Journals meet stricter editorial-vetting criteria (2+ years of
      peer-reviewed publishing, structured XML, content preservation).

    - **NLM Catalog only** (``is_medline: False``): ``confidence = 0.50``
      Broader NCBI coverage without the same depth of vetting.

    Absence from the PubMed NLM list does **not** generate a predatory signal
    — many legitimate niche journals and all non-biomedical venues are absent
    by design.
    """

    def __init__(self) -> None:
        """Initialize PubMed NLM backend with a 30-day cache TTL."""
        super().__init__(
            backend_name="pubmed_nlm",
            list_type=AssessmentType.LEGITIMATE,
            evidence_type=EvidenceType.LEGITIMATE_LIST,
            cache_ttl_hours=24 * 30,
            data_source_factory=lambda: PubMedNLMSource(),
        )

    def _calculate_match_confidence(
        self, query_input: QueryInput, raw_data: dict[str, Any]
    ) -> float:
        """Return confidence based on whether the entry is in the MEDLINE subset.

        MEDLINE-indexed journals receive a higher confidence score than
        journals found only in the broader NLM Catalog.

        Args:
            query_input: The original query (not used for this backend).
            raw_data: Matched journal entry dict containing ``metadata``.

        Returns:
            ``0.65`` for MEDLINE entries, ``0.50`` for NLM-Catalog-only entries.
        """
        is_medline = raw_data.get("metadata", {}).get("is_medline", False)
        return _CONFIDENCE_MEDLINE if is_medline else _CONFIDENCE_NLM_CATALOG


get_backend_registry().register_factory(
    "pubmed_nlm",
    lambda: PubMedBackend(),
    default_config={},
)
