# SPDX-License-Identifier: MIT
"""DOAJ (Directory of Open Access Journals) backend for legitimate journal verification."""

from typing import Any
from urllib.parse import quote

import aiohttp

from ..backend_exceptions import BackendError, RateLimitError
from ..confidence_utils import (
    MatchQuality,
    calculate_base_confidence,
    calculate_name_similarity,
    graduated_confidence,
)
from ..constants import CONFIDENCE_THRESHOLD_HIGH
from ..enums import AssessmentType, EvidenceType
from ..fallback_chain import FallbackStrategy, QueryFallbackChain
from ..fallback_executor import automatic_fallback
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..retry_utils import async_retry_with_backoff
from ..utils.dead_code import code_is_used
from .base import ApiBackendWithCache, get_backend_registry
from .fallback_mixin import FallbackStrategyMixin


detail_logger = get_detail_logger()
status_logger = get_status_logger()


DOAJ_MIN_CONFIDENCE_THRESHOLD = 0.5
DOAJ_WORD_SIMILARITY_THRESHOLD = 0.5
DOAJ_ALIAS_CONTAINS_MATCH_CONFIDENCE = 0.8


class DOAJBackend(ApiBackendWithCache, FallbackStrategyMixin):
    """Backend that checks DOAJ for legitimate open access journals."""

    def __init__(self, cache_ttl_hours: int = 24) -> None:
        """Initialize the DOAJ backend.

        Args:
            cache_ttl_hours: Time-to-live for cached results in hours. Defaults to 24.
        """
        super().__init__(cache_ttl_hours=cache_ttl_hours)
        self.base_url = "https://doaj.org/api/search/journals"

    def get_name(self) -> str:
        """Return the human-readable name of this backend.

        Returns:
            Backend identifier string ("doaj").
        """
        return "doaj"

    def get_evidence_type(self) -> EvidenceType:
        """Return the type of evidence this backend provides.

        Returns:
            EvidenceType.LEGITIMATE_LIST as DOAJ is a whitelist.
        """
        return EvidenceType.LEGITIMATE_LIST

    @code_is_used  # Called by ApiBackendWithCache.query()
    @automatic_fallback(
        [
            FallbackStrategy.ISSN,
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.FUZZY_NAME,
            FallbackStrategy.ALIASES,
        ]
    )
    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query DOAJ API with automatic fallback chain execution.

        Strategies executed in order:
        1. ISSN - primary ISSN identifier lookup
        2. NORMALIZED_NAME - exact journal name matching
        3. FUZZY_NAME - fuzzy journal name matching
        4. ALIASES - try alternative journal names

        The @automatic_fallback decorator handles all execution logic and
        calls the appropriate strategy handler methods automatically.

        Args:
            query_input: Normalized query input containing journal information

        Returns:
            BackendResult with assessment findings and fallback chain
        """
        # This method body is replaced by @automatic_fallback decorator
        # The NotImplementedError is never reached but satisfies mypy type checking
        raise NotImplementedError(
            "This method is handled by @automatic_fallback decorator"
        )

    @async_retry_with_backoff(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        exceptions=(RateLimitError, aiohttp.ClientError),
    )
    async def _fetch_from_doaj_api(
        self, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Fetch data from DOAJ API with retry logic for rate limits and network errors.

        Args:
            url: The API endpoint URL
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            RateLimitError: When API rate limit is hit
            aiohttp.ClientError: For network-related errors
            Exception: For other HTTP errors
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=30) as response:
                self._check_rate_limit_response(response)

                if response.status == 200:
                    result: dict[str, Any] = await response.json()
                    return result
                else:
                    # For other HTTP errors, don't retry
                    error_text = await response.text()
                    raise BackendError(
                        f"DOAJ API error: HTTP {response.status}. Response: {error_text[:200]}",
                        backend_name=self.get_name(),
                    )

    def _calculate_match_confidence(
        self, query_input: QueryInput, bibjson: dict[str, Any]
    ) -> float:
        """Calculate confidence score for a DOAJ match.

        Uses standard confidence utilities to determine match quality based on:
        1. ISSN Match
        2. Title Match (Exact, Substring, or Similarity)
        3. Alias Match

        Args:
            query_input: Normalized query input
            bibjson: DOAJ API result record

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # 1. ISSN match
        if query_input.identifiers.get("issn"):
            doaj_issn = bibjson.get("pissn") or bibjson.get("eissn")
            if doaj_issn == query_input.identifiers["issn"]:
                return calculate_base_confidence(MatchQuality.EXACT_ISSN)

        # 2. Title matching
        doaj_title = bibjson.get("title", "").lower()
        confidence = 0.0

        if query_input.normalized_name:
            query_title = query_input.normalized_name.lower()

            if doaj_title == query_title:
                confidence = calculate_base_confidence(MatchQuality.EXACT_NAME)
            elif query_title in doaj_title or doaj_title in query_title:
                confidence = calculate_base_confidence(MatchQuality.SUBSTRING_MATCH)
            else:
                # Word-based similarity
                similarity = calculate_name_similarity(query_title, doaj_title)
                if similarity > DOAJ_WORD_SIMILARITY_THRESHOLD:
                    base = calculate_base_confidence(MatchQuality.WORD_SIMILARITY)
                    confidence = graduated_confidence(
                        base, similarity, base, CONFIDENCE_THRESHOLD_HIGH
                    )

        # 3. Alias matching (if confidence is low)
        if confidence < DOAJ_ALIAS_CONTAINS_MATCH_CONFIDENCE:
            for alias in query_input.aliases:
                alias_lower = alias.lower()
                if alias_lower == doaj_title:
                    confidence = max(
                        confidence, calculate_base_confidence(MatchQuality.EXACT_ALIAS)
                    )
                elif alias_lower in doaj_title or doaj_title in alias_lower:
                    confidence = max(
                        confidence,
                        calculate_base_confidence(MatchQuality.SUBSTRING_MATCH),
                    )

        return min(confidence, 1.0)

    # Strategy handler implementations for automatic fallback framework
    async def _search_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Search DOAJ by ISSN/eISSN identifier.

        Args:
            issn: ISSN or eISSN identifier to search for

        Returns:
            First DOAJ result if found, None if no match
        """
        search_query = f"issn:{issn}"
        url = f"{self.base_url}/{quote(search_query, safe='')}"
        params = {"pageSize": 10}

        data = await self._fetch_from_doaj_api(url, params)
        results = data.get("results", [])
        result: dict[str, Any] | None = results[0] if results else None
        return result

    async def _search_by_name(
        self, name: str, exact: bool = True
    ) -> dict[str, Any] | None:
        """Search DOAJ by journal name.

        Args:
            name: Journal name to search for
            exact: Whether to use exact matching (True) or fuzzy matching (False)

        Returns:
            Best matching DOAJ result if found, None if no match
        """
        search_query = f'title:"{name}"'
        url = f"{self.base_url}/{quote(search_query, safe='')}"
        params = {"pageSize": 10}

        data = await self._fetch_from_doaj_api(url, params)
        results = data.get("results", [])

        if not results:
            return None

        if exact:
            # Filter for exact title matches
            name_lower = name.lower()
            for result in results:
                bibjson = result.get("bibjson", {})
                doaj_title = bibjson.get("title", "").lower()
                if doaj_title == name_lower:
                    matched_result: dict[str, Any] = result
                    return matched_result
            return None  # No exact match found
        else:
            # Fuzzy matching - return best result based on confidence
            best_result = None
            best_confidence = 0.0

            # Create a temporary QueryInput for confidence calculation
            temp_query = QueryInput(
                raw_input=name, normalized_name=name, identifiers={}, aliases=[]
            )

            for result in results:
                bibjson = result.get("bibjson", {})
                confidence = self._calculate_match_confidence(temp_query, bibjson)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_result = result

            # Return best result if it meets minimum threshold
            if best_confidence >= DOAJ_MIN_CONFIDENCE_THRESHOLD:
                final_result: dict[str, Any] | None = best_result
                return final_result
            else:
                return None

    def _build_success_result_with_chain(
        self,
        data: dict[str, Any],
        query_input: QueryInput,
        chain: QueryFallbackChain,
        response_time: float,
    ) -> BackendResult:
        """Build success result with populated fallback chain.

        Args:
            data: Raw DOAJ result data
            query_input: Original query input
            chain: Populated fallback chain
            response_time: Total response time

        Returns:
            BackendResult indicating successful match
        """
        bibjson = data.get("bibjson", {})
        confidence = self._calculate_match_confidence(query_input, bibjson)

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.FOUND,
            confidence=confidence,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "doaj_title": bibjson.get("title"),
                "doaj_issn": bibjson.get("pissn"),
                "doaj_eissn": bibjson.get("eissn"),
                "doaj_publisher": bibjson.get("publisher"),
                "doaj_subjects": [s.get("term") for s in bibjson.get("subject", [])],
                "doaj_url": bibjson.get("ref", {}).get("journal"),
                "match_confidence": confidence,
            },
            sources=["https://doaj.org"],
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
        """Build not found result with populated fallback chain.

        Args:
            query_input: Original query input
            chain: Populated fallback chain
            response_time: Total response time

        Returns:
            BackendResult indicating no match found
        """
        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={"query_params": "searched DOAJ database"},
            sources=["https://doaj.org"],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "doaj",
    lambda cache_ttl_hours=24: DOAJBackend(cache_ttl_hours=cache_ttl_hours),
    default_config={"cache_ttl_hours": 24},
)
