# SPDX-License-Identifier: MIT
"""OpenCitations backend with citation-footprint analysis."""

import asyncio
from typing import Any

import aiohttp

from ..backend_exceptions import BackendError, RateLimitError
from ..enums import AssessmentType, EvidenceType
from ..fallback_chain import FallbackStrategy, QueryFallbackChain
from ..fallback_executor import automatic_fallback
from ..logging_config import get_detail_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..retry_utils import async_retry_with_backoff
from ..utils.dead_code import code_is_used
from .base import ApiBackendWithCache, get_backend_registry
from .fallback_mixin import FallbackStrategyMixin


_API_TIMEOUT_SECONDS = 20
_DEFAULT_CACHE_TTL_HOURS = 24

_LARGE_CITATION_FOOTPRINT = 50_000
_MODERATE_CITATION_FOOTPRINT = 5_000
_MINIMAL_CITATION_FOOTPRINT = 500
_VERY_LOW_CITATION_REFERENCE_RATIO = 0.01
_RATIO_CHECK_MIN_REFERENCES = 5_000


class OpenCitationsAnalyzerBackend(ApiBackendWithCache, FallbackStrategyMixin):
    """Backend that analyzes OpenCitations venue-level citation metrics."""

    def __init__(self, cache_ttl_hours: int = _DEFAULT_CACHE_TTL_HOURS):
        """Initialize backend with configurable cache TTL."""
        super().__init__(cache_ttl_hours)
        self.base_url = "https://api.opencitations.net/index/v2"
        self.detail_logger = get_detail_logger()

    def get_name(self) -> str:
        """Return backend name."""
        return "opencitations_analyzer"

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type."""
        return EvidenceType.HEURISTIC

    @code_is_used  # Called by ApiBackendWithCache.query()
    @automatic_fallback([FallbackStrategy.ISSN, FallbackStrategy.EISSN])
    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query OpenCitations API using identifier-based fallback strategies."""
        raise NotImplementedError(
            "This method is handled by @automatic_fallback decorator"
        )

    async def _search_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Search OpenCitations by ISSN/eISSN identifier."""
        self.detail_logger.debug(f"OpenCitations: Searching by ISSN {issn}")
        return await self._fetch_venue_metrics_by_issn(issn)

    async def _search_by_name(self, name: str, exact: bool = True) -> Any | None:
        """Search by venue name.

        OpenCitations v2 API is identifier-driven for the metrics used here.
        """
        return None

    @async_retry_with_backoff(
        max_retries=3,
        exceptions=(RateLimitError, aiohttp.ClientError, asyncio.TimeoutError),
    )
    async def _fetch_venue_metrics_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Fetch venue-level citation/reference metrics for an ISSN."""
        citation_url = f"{self.base_url}/venue-citation-count/issn:{issn}"
        reference_url = f"{self.base_url}/venue-reference-count/issn:{issn}"

        citation_count, reference_count = await asyncio.gather(
            self._fetch_count_from_url(citation_url),
            self._fetch_count_from_url(reference_url),
        )

        if citation_count is None and reference_count is None:
            return None

        if (citation_count or 0) == 0 and (reference_count or 0) == 0:
            return None

        return {
            "issn": issn,
            "citation_count": citation_count or 0,
            "reference_count": reference_count or 0,
            "citation_count_url": citation_url,
            "reference_count_url": reference_url,
        }

    async def _fetch_count_from_url(self, url: str) -> int | None:
        """Fetch a count value from a specific OpenCitations endpoint URL."""
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_API_TIMEOUT_SECONDS)
        ) as session:
            async with session.get(url) as response:
                self._check_rate_limit_response(response)

                if response.status == 200:
                    payload = await response.json()
                    return self._parse_count_payload(payload)
                if response.status == 404:
                    return None

                error_text = await response.text()
                raise BackendError(
                    (
                        f"OpenCitations API returned status {response.status}. "
                        f"Response: {error_text[:200]}"
                    ),
                    backend_name=self.get_name(),
                )

    def _parse_count_payload(self, payload: Any) -> int | None:
        """Parse count payloads from OpenCitations count endpoints."""
        if isinstance(payload, list):
            if not payload:
                return None
            if isinstance(payload[0], dict):
                for key in ("count", "citation_count", "reference_count"):
                    value = payload[0].get(key)
                    parsed = self._safe_int(value)
                    if parsed is not None:
                        return parsed
            return None

        if isinstance(payload, dict):
            for key in ("count", "citation_count", "reference_count"):
                value = payload.get(key)
                parsed = self._safe_int(value)
                if parsed is not None:
                    return parsed

        return None

    def _safe_int(self, value: Any) -> int | None:
        """Safely parse integer values from API payload fields."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(stripped)
            except ValueError:
                return None
        return None

    def _analyze_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Analyze OpenCitations metrics and derive assessment heuristics."""
        citation_count = int(metrics.get("citation_count", 0) or 0)
        reference_count = int(metrics.get("reference_count", 0) or 0)
        ratio = citation_count / reference_count if reference_count > 0 else None

        red_flags: list[str] = []
        green_flags: list[str] = []
        reasoning: list[str] = []

        if citation_count >= _LARGE_CITATION_FOOTPRINT:
            green_flags.append(
                f"Large OpenCitations citation footprint: {citation_count:,} citations"
            )
        elif citation_count >= _MODERATE_CITATION_FOOTPRINT:
            green_flags.append(
                f"Moderate OpenCitations citation footprint: {citation_count:,} citations"
            )
        elif citation_count >= _MINIMAL_CITATION_FOOTPRINT:
            green_flags.append(
                f"Non-trivial OpenCitations citation footprint: {citation_count:,} citations"
            )

        if (
            ratio is not None
            and reference_count >= _RATIO_CHECK_MIN_REFERENCES
            and ratio < _VERY_LOW_CITATION_REFERENCE_RATIO
        ):
            red_flags.append(
                f"Very low citation/reference ratio in OpenCitations: {ratio:.3f}"
            )

        if green_flags:
            reasoning.append("OpenCitations positive indicators:")
            reasoning.extend([f"  • {flag}" for flag in green_flags])
        if red_flags:
            reasoning.append("OpenCitations warning signs:")
            reasoning.extend([f"  • {flag}" for flag in red_flags])

        if citation_count >= _MODERATE_CITATION_FOOTPRINT:
            assessment = AssessmentType.LEGITIMATE
            confidence = 0.75
        elif citation_count >= _MINIMAL_CITATION_FOOTPRINT:
            assessment = AssessmentType.LEGITIMATE
            confidence = 0.65
        elif citation_count > 0:
            assessment = AssessmentType.LEGITIMATE
            confidence = 0.55
        else:
            assessment = AssessmentType.UNKNOWN
            confidence = 0.30
            reasoning.append(
                "OpenCitations has limited citation evidence for this venue"
            )

        return {
            "assessment": assessment,
            "confidence": confidence,
            "red_flags": red_flags,
            "green_flags": green_flags,
            "reasoning": reasoning,
            "metrics": {
                "citation_count": citation_count,
                "reference_count": reference_count,
                "citation_reference_ratio": ratio,
            },
        }

    def _build_success_result_with_chain(
        self,
        opencitations_data: dict[str, Any],
        query_input: QueryInput,
        chain: QueryFallbackChain,
        response_time: float,
    ) -> BackendResult:
        """Build successful backend result from OpenCitations metrics."""
        analysis = self._analyze_metrics(opencitations_data)

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.FOUND,
            confidence=analysis["confidence"],
            assessment=analysis["assessment"],
            data={
                "opencitations_data": opencitations_data,
                "analysis": analysis,
                "metrics": analysis["metrics"],
                "red_flags": analysis["red_flags"],
                "green_flags": analysis["green_flags"],
            },
            sources=[
                opencitations_data.get("citation_count_url", ""),
                opencitations_data.get("reference_count_url", ""),
            ],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )

    def _build_not_found_result_with_chain(
        self,
        query_input: QueryInput,
        chain: QueryFallbackChain,
        response_time: float,
    ) -> BackendResult:
        """Build not-found result when OpenCitations has no usable venue metrics."""
        normalization = query_input.normalization_result
        searched_for = (
            normalization.name if normalization and normalization.name else None
        )
        if not searched_for:
            searched_for = (
                normalization.original_text if normalization else query_input.raw_input
            )
        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={
                "searched_for": searched_for,
                "issn": normalization.issn if normalization else None,
                "eissn": normalization.eissn if normalization else None,
            },
            sources=["https://api.opencitations.net/index/v2"],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )


# Register backend with factory for configuration support
get_backend_registry().register_factory(
    "opencitations_analyzer",
    lambda cache_ttl_hours=24: OpenCitationsAnalyzerBackend(
        cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"cache_ttl_hours": 24},
)
