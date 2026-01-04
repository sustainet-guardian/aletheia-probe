# SPDX-License-Identifier: MIT
"""DOAJ (Directory of Open Access Journals) backend for legitimate journal verification."""

import asyncio
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from ..enums import AssessmentType, EvidenceType
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..retry_utils import async_retry_with_backoff
from ..utils.dead_code import code_is_used
from .base import ApiBackendWithCache, get_backend_registry


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RateLimitError(Exception):
    """Raised when DOAJ API rate limit is hit."""

    @code_is_used
    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"DOAJ API rate limit hit. Retry after {retry_after}s")


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

        Args:
            query_input: Normalized query input with journal information.

        Returns:
            BackendResult with findings from DOAJ.
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

        except RateLimitError as e:
            status_logger.warning(f"DOAJ API rate limit exceeded: {e}")
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.RATE_LIMITED,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=time.time() - start_time,
            )
        except aiohttp.ClientError as e:
            status_logger.error(f"DOAJ API network error: {e}")
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=f"Network error: {str(e)}",
                response_time=time.time() - start_time,
            )
        except Exception as e:
            status_logger.error(f"DOAJ API unexpected error: {e}")
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=f"Unexpected error: {str(e)}",
                response_time=time.time() - start_time,
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
                if response.status == 200:
                    result: dict[str, Any] = await response.json()
                    return result
                elif response.status == 429:
                    # Handle rate limiting with Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    retry_seconds = int(retry_after) if retry_after else 60

                    detail_logger.debug(
                        f"DOAJ API rate limit hit. Retry-After: {retry_seconds}s. URL: {url}"
                    )

                    # Wait for the specified time before raising exception for retry
                    await asyncio.sleep(retry_seconds)
                    raise RateLimitError(retry_after=retry_seconds)
                else:
                    # For other HTTP errors, don't retry
                    error_text = await response.text()
                    raise Exception(
                        f"DOAJ API error: HTTP {response.status}. Response: {error_text[:200]}"
                    )

    def _process_doaj_response(
        self,
        query_input: QueryInput,
        response_data: dict[str, Any],
        response_time: float,
    ) -> BackendResult:
        """Process DOAJ API response and determine match quality.

        Args:
            query_input: The original query input.
            response_data: JSON response from DOAJ API.
            response_time: Time taken for the API request in seconds.

        Returns:
            BackendResult with the processed assessment.
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

        if best_match and best_confidence > 0.5:  # Minimum confidence threshold
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

        Args:
            query_input: The original query input.
            bibjson: The bibjson part of a DOAJ result record.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        confidence = 0.0

        # ISSN match (highest confidence)
        if query_input.identifiers.get("issn"):
            doaj_issn = bibjson.get("pissn") or bibjson.get("eissn")
            if doaj_issn == query_input.identifiers["issn"]:
                return 0.98  # Very high confidence for ISSN match

        # Title matching
        doaj_title = bibjson.get("title", "").lower()
        if query_input.normalized_name:
            query_title = query_input.normalized_name.lower()

            # Exact title match
            if doaj_title == query_title:
                confidence = 0.95
            # Check if titles contain each other
            elif query_title in doaj_title or doaj_title in query_title:
                confidence = 0.85
            else:
                # Word-based similarity
                query_words = set(query_title.split())
                doaj_words = set(doaj_title.split())

                if query_words and doaj_words:
                    intersection = query_words & doaj_words
                    union = query_words | doaj_words
                    word_similarity = len(intersection) / len(union)

                    # Only consider it a match if significant overlap
                    if word_similarity > 0.5:
                        confidence = 0.6 + (word_similarity * 0.25)

        # Check aliases if main title didn't match well
        if confidence < 0.8:
            for alias in query_input.aliases:
                alias_lower = alias.lower()
                if alias_lower == doaj_title:
                    confidence = max(confidence, 0.9)
                elif alias_lower in doaj_title or doaj_title in alias_lower:
                    confidence = max(confidence, 0.8)

        return min(confidence, 1.0)


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "doaj",
    lambda cache_ttl_hours=24: DOAJBackend(cache_ttl_hours=cache_ttl_hours),
    default_config={"cache_ttl_hours": 24},
)
