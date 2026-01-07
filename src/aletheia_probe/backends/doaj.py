# SPDX-License-Identifier: MIT
"""DOAJ (Directory of Open Access Journals) backend for legitimate journal verification."""

import time
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
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..retry_utils import async_retry_with_backoff
from .base import ApiBackendWithCache, get_backend_registry


detail_logger = get_detail_logger()
status_logger = get_status_logger()


DOAJ_MIN_CONFIDENCE_THRESHOLD = 0.5
DOAJ_WORD_SIMILARITY_THRESHOLD = 0.5
DOAJ_ALIAS_CONTAINS_MATCH_CONFIDENCE = 0.8


class DOAJBackend(ApiBackendWithCache):
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

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query DOAJ API for journal information with retry logic.

        Constructs a search query based on available identifiers (ISSN) or the
        journal name, executes the API request with automatic retries for
        transient failures, and hands off the response for processing.

        Args:
            query_input: Normalized query input containing the journal's name
                and identifiers used to build the DOAJ search query.

        Returns:
            BackendResult containing the assessment findings, or a failure result
            if errors occurred during the API communication.
        """
        start_time = time.time()

        try:
            # Build search query for URL path
            if query_input.identifiers.get("issn"):
                search_query = f"issn:{query_input.identifiers['issn']}"
            elif query_input.normalized_name:
                # Search by journal title - encode spaces for URL
                search_query = f'title:"{query_input.normalized_name}"'
            else:
                # Fallback to raw input
                search_query = f'title:"{query_input.raw_input}"'

            # Construct full URL with search query in path (URL encoded)
            url = f"{self.base_url}/{quote(search_query, safe='')}"
            params = {"pageSize": 10}  # Limit results

            # Use retry logic for the API call
            data = await self._fetch_from_doaj_api(url, params)
            return self._process_doaj_response(
                query_input, data, time.time() - start_time
            )

        except Exception as e:
            status_logger.error(f"DOAJ API error: {e}")
            return self._build_error_result(e, time.time() - start_time)

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

    def _process_doaj_response(
        self,
        query_input: QueryInput,
        response_data: dict[str, Any],
        response_time: float,
    ) -> BackendResult:
        """Process DOAJ API response and determine match quality.

        Iterates through the search results from DOAJ, calculates match confidence
        for each, and selects the best match. If the best match exceeds the
        minimum confidence threshold, the journal is assessed as legitimate.

        Args:
            query_input: The original query input containing journal information
                like name and ISSN.
            response_data: JSON response data received from the DOAJ API search.
            response_time: Total time taken for the API request in seconds.

        Returns:
            BackendResult containing the assessment status (FOUND, NOT_FOUND),
            confidence score, and detailed metadata if a match was found.
        """
        results = response_data.get("results", [])

        if not results:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={"query_params": "searched DOAJ database"},
                sources=["https://doaj.org"],
                error_message=None,
                response_time=response_time,
            )

        # Find the best match
        best_match = None
        best_confidence = 0.0

        for result in results:
            bibjson = result.get("bibjson", {})
            confidence = self._calculate_match_confidence(query_input, bibjson)

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = result

        if (
            best_match and best_confidence > DOAJ_MIN_CONFIDENCE_THRESHOLD
        ):  # Minimum confidence threshold
            bibjson = best_match.get("bibjson", {})

            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.FOUND,
                confidence=best_confidence,
                assessment=AssessmentType.LEGITIMATE,
                data={
                    "doaj_title": bibjson.get("title"),
                    "doaj_issn": bibjson.get("pissn"),
                    "doaj_eissn": bibjson.get("eissn"),
                    "doaj_publisher": bibjson.get("publisher"),
                    "doaj_subjects": [
                        s.get("term") for s in bibjson.get("subject", [])
                    ],
                    "doaj_url": bibjson.get("ref", {}).get("journal"),
                    "total_results": len(results),
                    "match_confidence": best_confidence,
                },
                sources=["https://doaj.org"],
                error_message=None,
                response_time=response_time,
            )
        else:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={
                    "total_results": len(results),
                    "best_match_confidence": best_confidence,
                    "reason": "No high-confidence matches found",
                },
                sources=["https://doaj.org"],
                error_message=None,
                response_time=response_time,
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


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "doaj",
    lambda cache_ttl_hours=24: DOAJBackend(cache_ttl_hours=cache_ttl_hours),
    default_config={"cache_ttl_hours": 24},
)
