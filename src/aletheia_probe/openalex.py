# SPDX-License-Identifier: MIT
"""OpenAlex API client for fetching publication volume data."""

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from aletheia_probe.normalizer import input_normalizer

from .backend_exceptions import RateLimitError
from .logging_config import get_detail_logger
from .retry_utils import async_retry_with_backoff


detail_logger = get_detail_logger()


# Scoring weights
SCORE_NAME_EXACT_MATCH = 0.4
SCORE_NAME_PARTIAL_MATCH = 0.2

SCORE_VOLUME_HIGH = 0.3
SCORE_VOLUME_MEDIUM = 0.2
SCORE_VOLUME_LOW = 0.1

SCORE_CITATION_HIGH = 0.2
SCORE_CITATION_MEDIUM = 0.15
SCORE_CITATION_LOW = 0.1

SCORE_RECENCY_ACTIVE = 0.1

# Penalties (multipliers)
PENALTY_VERY_FEW_PAPERS = 0.2
PENALTY_LOW_IMPACT = 0.5
PENALTY_OLD_SOURCE = 0.5
PENALTY_SHORT_SPAN_CONFERENCE = 0.4

# Conference Bonuses
BONUS_CONF_MAJOR = 0.15
BONUS_CONF_GOOD = 0.05
BONUS_CONF_LONG_RUNNING = 0.1


class OpenAlexClient:
    """Client for OpenAlex API to fetch journal publication statistics."""

    BASE_URL = "https://api.openalex.org"

    def __init__(
        self, email: str = "noreply@aletheia-probe.org", max_concurrent: int = 10
    ):
        """Initialize OpenAlex client.

        Args:
            email: Email for polite pool access (recommended for higher rate limits)
            max_concurrent: Maximum concurrent API requests
        """
        self.email = email
        self.headers = {"User-Agent": f"AletheiaProbe/1.0 (mailto:{email})"}
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "OpenAlexClient":
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    @async_retry_with_backoff(
        max_retries=3,
        exceptions=(RateLimitError, aiohttp.ClientError, asyncio.TimeoutError),
    )
    async def get_source_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Get journal source information by ISSN.

        Args:
            issn: ISSN to search for (can be print or electronic)

        Returns:
            Dictionary with source information or None if not found
        """
        async with self.semaphore:
            url = f"{self.BASE_URL}/sources?filter=issn:{issn}"

            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
                )

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        return dict(results[0])
                    else:
                        detail_logger.debug(f"No OpenAlex source found for ISSN {issn}")
                        return None
                elif response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_seconds = int(retry_after) if retry_after else None
                    raise RateLimitError(
                        message="OpenAlex rate limit hit",
                        retry_after=retry_seconds,
                        backend_name="openalex",
                    )
                else:
                    raise aiohttp.ClientError(
                        f"OpenAlex API returned status {response.status} for ISSN {issn}"
                    )

    def _score_source_match(self, source: dict[str, Any], journal_name: str) -> float:
        """Score how well a source matches the journal name.

        Args:
            source: OpenAlex source record
            journal_name: Journal name being searched

        Returns:
            Score between 0 and 1 (higher = better match)
        """
        display_name = source.get("display_name", "").lower()
        search_name = journal_name.lower()
        works_count = source.get("works_count", 0)
        cited_by_count = source.get("cited_by_count", 0)
        first_year = source.get("first_publication_year")
        last_year = source.get("last_publication_year")
        source_type = source.get("type", "")

        score = 0.0

        # Name matching (40% of score)
        if search_name in display_name or display_name in search_name:
            score += SCORE_NAME_EXACT_MATCH
        elif any(word in display_name for word in search_name.split() if len(word) > 3):
            score += SCORE_NAME_PARTIAL_MATCH

        # Publication volume (30% of score)
        if works_count > 1000:
            score += SCORE_VOLUME_HIGH
        elif works_count > 100:
            score += SCORE_VOLUME_MEDIUM
        elif works_count > 10:
            score += SCORE_VOLUME_LOW
        elif works_count <= 2:
            score *= (
                PENALTY_VERY_FEW_PAPERS  # Heavily penalize sources with very few papers
            )

        # Citation impact (20% of score)
        if cited_by_count > 50000:
            score += SCORE_CITATION_HIGH
        elif cited_by_count > 10000:
            score += SCORE_CITATION_MEDIUM
        elif cited_by_count > 1000:
            score += SCORE_CITATION_LOW
        elif cited_by_count <= 10:
            score *= PENALTY_LOW_IMPACT  # Penalize low-impact sources

        # Enhanced conference scoring: Consider quality metrics before penalizing short spans
        if source_type == "conference" and first_year and last_year:
            years_active = last_year - first_year + 1

            # Determine if this is a high-quality conference instance
            is_high_quality = (cited_by_count > 50000) or (works_count > 1000)
            is_medium_quality = (cited_by_count > 10000) or (works_count > 500)

            if years_active <= 2:
                # High-quality single-year instances are legitimate (e.g., CVPR 2022)
                if is_high_quality:
                    score += BONUS_CONF_MAJOR  # Bonus for major conference instance
                elif is_medium_quality:
                    score += BONUS_CONF_GOOD  # Small bonus for good conference instance
                else:
                    # Only penalize low-quality short-span conferences
                    score *= PENALTY_SHORT_SPAN_CONFERENCE  # Reduced penalty (was 0.3)
            elif years_active >= 10:
                score += BONUS_CONF_LONG_RUNNING  # Bonus for long-running venues

        # Recency (10% of score) - penalize inactive sources
        if last_year:
            current_year = datetime.now().year
            if last_year >= current_year - 2:
                score += SCORE_RECENCY_ACTIVE
            elif last_year < current_year - 10:
                score *= PENALTY_OLD_SOURCE  # Penalize very old sources

        return min(score, 1.0)

    @async_retry_with_backoff(
        max_retries=3,
        exceptions=(RateLimitError, aiohttp.ClientError, asyncio.TimeoutError),
    )
    async def get_source_by_name(
        self, journal_name: str, is_series_lookup: bool = False
    ) -> dict[str, Any] | None:
        """Get journal source information by name search with improved matching.

        Args:
            journal_name: Journal name to search for
            is_series_lookup: Whether this lookup is for a conference series name

        Returns:
            Dictionary with source information or None if not found
        """
        async with self.semaphore:
            # Use search endpoint for fuzzy matching
            url = f"{self.BASE_URL}/sources?search={journal_name}"

            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
                )

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        # Score all results and pick the best match
                        scored_results = [
                            (self._score_source_match(result, journal_name), result)
                            for result in results
                        ]
                        scored_results.sort(key=lambda x: x[0], reverse=True)

                        best_score, best_result = scored_results[0]

                        # Only return result if it has a reasonable score
                        if best_score > 0.1:
                            detail_logger.debug(
                                f"Selected OpenAlex source for '{journal_name}': "
                                f"{best_result.get('display_name')} (score: {best_score:.2f})"
                            )
                            if is_series_lookup:
                                best_result["is_series_match"] = True
                            return dict(best_result)
                        else:
                            detail_logger.debug(
                                f"No good OpenAlex source match for '{journal_name}' "
                                f"(best score: {best_score:.2f})"
                            )
                            return None
                    else:
                        detail_logger.debug(
                            f"No OpenAlex source found for name '{journal_name}'"
                        )
                        return None
                elif response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_seconds = int(retry_after) if retry_after else None
                    raise RateLimitError(
                        message="OpenAlex rate limit hit",
                        retry_after=retry_seconds,
                        backend_name="openalex",
                    )
                else:
                    raise aiohttp.ClientError(
                        f"OpenAlex API returned status {response.status} for name '{journal_name}'"
                    )

    @async_retry_with_backoff(
        max_retries=3,
        exceptions=(RateLimitError, aiohttp.ClientError, asyncio.TimeoutError),
    )
    async def get_institution_by_id(self, institution_id: str) -> dict[str, Any] | None:
        """Get institution record by OpenAlex institution ID/URL.

        Args:
            institution_id: OpenAlex institution identifier (URL or ``I...`` ID).

        Returns:
            Institution payload dictionary, or None if not found.
        """
        async with self.semaphore:
            normalized_id = institution_id.strip()
            if not normalized_id:
                return None
            if normalized_id.startswith("https://openalex.org/"):
                normalized_id = normalized_id.rsplit("/", 1)[-1]
            if not normalized_id.startswith("I"):
                return None

            url = f"{self.BASE_URL}/institutions/{normalized_id}"

            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
                )

            async with self.session.get(url) as response:
                if response.status == 200:
                    payload = await response.json()
                    return dict(payload) if isinstance(payload, dict) else None
                if response.status == 404:
                    return None
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_seconds = int(retry_after) if retry_after else None
                    raise RateLimitError(
                        message="OpenAlex rate limit hit",
                        retry_after=retry_seconds,
                        backend_name="openalex",
                    )
                raise aiohttp.ClientError(
                    f"OpenAlex API returned status {response.status} for institution {normalized_id}"
                )

    @async_retry_with_backoff(
        max_retries=3,
        exceptions=(RateLimitError, aiohttp.ClientError, asyncio.TimeoutError),
    )
    async def get_works_count_by_year(
        self,
        source_id: str,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> dict[int, int]:
        """Get publication counts by year for a source.

        Args:
            source_id: OpenAlex source ID (e.g., 'S137773608')
            start_year: Start year for filtering (default: current_year - 5)
            end_year: End year for filtering (default: current_year)

        Returns:
            Dictionary mapping year -> count
        """
        async with self.semaphore:
            current_year = datetime.now().year

            if start_year is None:
                start_year = current_year - 5
            if end_year is None:
                end_year = current_year

            # Ensure source_id has 'S' prefix
            if not source_id.startswith("S"):
                source_id = f"S{source_id}"

            url = (
                f"{self.BASE_URL}/works?"
                f"filter=primary_location.source.id:https://openalex.org/{source_id},"
                f"publication_year:{start_year}-{end_year}&"
                f"group_by=publication_year&per-page=200"
            )

            if not self.session:
                self.session = aiohttp.ClientSession(
                    headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
                )

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        int(item["key"]): item["count"]
                        for item in data.get("group_by", [])
                        if item["key"] and item["key"].isdigit()
                    }
                elif response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    retry_seconds = int(retry_after) if retry_after else None
                    raise RateLimitError(
                        message="OpenAlex rate limit hit",
                        retry_after=retry_seconds,
                        backend_name="openalex",
                    )
                else:
                    raise aiohttp.ClientError(
                        f"OpenAlex API returned status {response.status} for source {source_id}"
                    )

    async def enrich_journal_data(
        self, journal_name: str, issn: str | None = None, eissn: str | None = None
    ) -> dict[str, Any] | None:
        """Enrich journal data with publication counts from OpenAlex.

        Args:
            journal_name: Journal name
            issn: Print ISSN (if available)
            eissn: Electronic ISSN (if available)

        Returns:
            Dictionary with publication statistics or None if not found
        """
        source = None

        # Try ISSN first (most reliable)
        if issn:
            source = await self.get_source_by_issn(issn)

        # Try eISSN if ISSN failed
        if not source and eissn:
            source = await self.get_source_by_issn(eissn)

        # Fall back to name search if no ISSN match
        if not source and journal_name:
            source = await self.get_source_by_name(journal_name)

            # Fallback to series name if full name fails
            if not source:
                try:
                    series_name = input_normalizer.extract_conference_series(
                        journal_name
                    )
                    if series_name and series_name != journal_name:
                        detail_logger.debug(
                            f"Attempting series fallback for '{journal_name}' -> '{series_name}'"
                        )
                        source = await self.get_source_by_name(
                            series_name, is_series_lookup=True
                        )
                        if source:
                            detail_logger.debug(
                                f"Series fallback successful: found '{source.get('display_name')}'"
                            )
                        else:
                            detail_logger.debug(
                                f"Series fallback failed: no match for '{series_name}'"
                            )
                    else:
                        detail_logger.debug(
                            f"Skipping series fallback for '{journal_name}': "
                            f"series name {'not extractable' if not series_name else 'identical'}"
                        )
                except (
                    AttributeError,
                    ValueError,
                    TypeError,
                    aiohttp.ClientError,
                ) as e:
                    detail_logger.warning(
                        f"Error during conference series extraction for '{journal_name}': {e}"
                    )

        if not source:
            detail_logger.debug(f"No OpenAlex data found for journal '{journal_name}'")
            return None

        # Extract source ID
        source_id_full = source.get("id", "")
        source_id = source_id_full.split("/")[-1] if source_id_full else None

        if not source_id:
            detail_logger.warning(
                f"No source ID in OpenAlex response for '{journal_name}'"
            )
            return None

        # Get total works count
        total_works = source.get("works_count", 0)

        # Get recent publication counts (last 5 years)
        current_year = datetime.now().year
        recent_counts = await self.get_works_count_by_year(
            source_id, start_year=current_year - 5, end_year=current_year
        )

        # Calculate recent total
        recent_total = sum(recent_counts.values())

        return {
            "openalex_id": source_id,
            "openalex_url": source_id_full,
            "display_name": source.get("display_name"),
            "source_type": source.get("type"),
            "issn_l": source.get("issn_l"),
            "issns": source.get("issn", []),
            "total_publications": total_works,
            "recent_publications": recent_total,
            "recent_publications_by_year": recent_counts,
            "publisher": source.get("host_organization_name"),
            "first_publication_year": source.get("first_publication_year"),
            "last_publication_year": source.get("last_publication_year"),
            "cited_by_count": source.get("cited_by_count", 0),
            "is_in_doaj": source.get("is_in_doaj", False),
            "fetched_at": datetime.now().isoformat(),
        }


# Convenience function for one-off enrichment
async def get_publication_stats(
    journal_name: str, issn: str | None = None, eissn: str | None = None
) -> dict[str, Any] | None:
    """Get publication statistics for a single journal.

    Args:
        journal_name: Journal name
        issn: Print ISSN
        eissn: Electronic ISSN

    Returns:
        Dictionary with publication statistics or None
    """
    try:
        async with OpenAlexClient() as client:
            return await client.enrich_journal_data(journal_name, issn, eissn)
    except (aiohttp.ClientError, ValueError, KeyError, AttributeError) as e:
        detail_logger.error(f"Error getting publication stats: {e}")
        return None
