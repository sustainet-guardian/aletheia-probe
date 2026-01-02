# SPDX-License-Identifier: MIT
"""OpenAlex API client for fetching publication volume data."""

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from aletheia_probe.normalizer import input_normalizer

from .logging_config import get_detail_logger


detail_logger = get_detail_logger()


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

    async def get_source_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Get journal source information by ISSN.

        Args:
            issn: ISSN to search for (can be print or electronic)

        Returns:
            Dictionary with source information or None if not found
        """
        async with self.semaphore:
            url = f"{self.BASE_URL}/sources?filter=issn:{issn}"

            try:
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
                            detail_logger.debug(
                                f"No OpenAlex source found for ISSN {issn}"
                            )
                    elif response.status == 429:
                        detail_logger.warning(
                            f"OpenAlex rate limit hit for ISSN {issn}"
                        )
                    else:
                        detail_logger.warning(
                            f"OpenAlex API returned status {response.status} for ISSN {issn}"
                        )

            except asyncio.TimeoutError:
                detail_logger.warning(f"OpenAlex API timeout for ISSN {issn}")
            except (aiohttp.ClientError, ValueError, KeyError) as e:
                detail_logger.error(
                    f"Error fetching OpenAlex data for ISSN {issn}: {e}"
                )

        return None

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
            score += 0.4
        elif any(word in display_name for word in search_name.split() if len(word) > 3):
            score += 0.2

        # Publication volume (30% of score)
        if works_count > 1000:
            score += 0.3
        elif works_count > 100:
            score += 0.2
        elif works_count > 10:
            score += 0.1
        elif works_count <= 2:
            score *= 0.2  # Heavily penalize sources with very few papers

        # Citation impact (20% of score)
        if cited_by_count > 50000:
            score += 0.2
        elif cited_by_count > 10000:
            score += 0.15
        elif cited_by_count > 1000:
            score += 0.1
        elif cited_by_count <= 10:
            score *= 0.5  # Penalize low-impact sources

        # Enhanced conference scoring: Consider quality metrics before penalizing short spans
        if source_type == "conference" and first_year and last_year:
            years_active = last_year - first_year + 1

            # Determine if this is a high-quality conference instance
            is_high_quality = (cited_by_count > 50000) or (works_count > 1000)
            is_medium_quality = (cited_by_count > 10000) or (works_count > 500)

            if years_active <= 2:
                # High-quality single-year instances are legitimate (e.g., CVPR 2022)
                if is_high_quality:
                    score += 0.15  # Bonus for major conference instance
                elif is_medium_quality:
                    score += 0.05  # Small bonus for good conference instance
                else:
                    # Only penalize low-quality short-span conferences
                    score *= 0.4  # Reduced penalty (was 0.3)
            elif years_active >= 10:
                score += 0.1  # Bonus for long-running venues

        # Recency (10% of score) - penalize inactive sources
        if last_year:
            current_year = datetime.now().year
            if last_year >= current_year - 2:
                score += 0.1
            elif last_year < current_year - 10:
                score *= 0.5  # Penalize very old sources

        return min(score, 1.0)

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

            try:
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
                        else:
                            detail_logger.debug(
                                f"No OpenAlex source found for name '{journal_name}'"
                            )
                    elif response.status == 429:
                        detail_logger.warning(
                            f"OpenAlex rate limit hit for name '{journal_name}'"
                        )
                    else:
                        detail_logger.warning(
                            f"OpenAlex API returned status {response.status} for name '{journal_name}'"
                        )

            except asyncio.TimeoutError:
                detail_logger.warning(f"OpenAlex API timeout for name '{journal_name}'")
            except (aiohttp.ClientError, ValueError, KeyError) as e:
                detail_logger.error(
                    f"Error fetching OpenAlex data for name '{journal_name}': {e}"
                )

        return None

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

            try:
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
                        detail_logger.warning(
                            f"OpenAlex rate limit hit for source {source_id}"
                        )
                    else:
                        detail_logger.warning(
                            f"OpenAlex API returned status {response.status} for source {source_id}"
                        )

            except asyncio.TimeoutError:
                detail_logger.warning(f"OpenAlex API timeout for source {source_id}")
            except (aiohttp.ClientError, ValueError, KeyError) as e:
                detail_logger.error(
                    f"Error fetching works count for source {source_id}: {e}"
                )

        return {}

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

            # NEW: Fallback to series name if full name fails
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

    async def enrich_batch(
        self,
        journals: list[dict[str, Any]],
        batch_size: int = 50,
        delay_between_batches: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Enrich multiple journals with OpenAlex data in batches.

        Args:
            journals: List of journal dictionaries with 'journal_name' and optionally 'issn'/'eissn'
            batch_size: Number of journals to process concurrently
            delay_between_batches: Delay in seconds between batches (to respect rate limits)

        Returns:
            List of enriched journal dictionaries
        """
        enriched = []

        for i in range(0, len(journals), batch_size):
            batch = journals[i : i + batch_size]

            # Process batch concurrently
            tasks = [
                self.enrich_journal_data(
                    journal.get("journal_name", ""),
                    journal.get("issn"),
                    journal.get("eissn"),
                )
                for journal in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Combine results with original journal data
            for journal, openalex_data in zip(batch, results, strict=True):
                if isinstance(openalex_data, Exception):
                    detail_logger.error(
                        f"Error enriching journal '{journal.get('journal_name')}': {openalex_data}"
                    )
                    journal["openalex_data"] = None
                else:
                    journal["openalex_data"] = openalex_data

                enriched.append(journal)

            # Delay between batches to be polite to the API
            if i + batch_size < len(journals):
                await asyncio.sleep(delay_between_batches)

            # Log progress
            detail_logger.info(
                f"Enriched {min(i + batch_size, len(journals))}/{len(journals)} journals with OpenAlex data"
            )

        return enriched


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


