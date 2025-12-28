# SPDX-License-Identifier: MIT
"""Retraction Watch backend for journal quality assessment based on retraction data."""

import asyncio
import time
from typing import Any

import aiohttp

from ..cache import RetractionCache
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..openalex import get_publication_stats
from .base import HybridBackend, get_backend_registry


detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RetractionWatchBackend(HybridBackend):
    """Backend that checks retraction history from Retraction Watch database."""

    def __init__(self, cache_ttl_hours: int = 24) -> None:
        """Initialize backend with configurable cache TTL.

        Args:
            cache_ttl_hours: Cache time-to-live in hours (default: 24)
        """
        super().__init__(cache_ttl_hours=cache_ttl_hours)
        self.source_name = "retraction_watch"
        self.list_type = "quality_indicator"

    def get_name(self) -> str:
        return "retraction_watch"

    def get_description(self) -> str:
        return "Checks journal retraction history from Retraction Watch database"

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query retraction data for journal information.

        This method performs the actual query against the Retraction Watch database
        and OpenAlex API. Results are automatically cached by the HybridBackend parent.

        Args:
            query_input: Normalized query input with journal information

        Returns:
            BackendResult with retraction assessment and metadata
        """
        start_time = time.time()

        try:
            # Use parent's search methods for consistency
            # Search by ISSN first (though we don't have ISSN in retraction data)
            if query_input.identifiers.get("issn"):
                results = self.journal_cache.search_journals(
                    issn=query_input.identifiers["issn"],
                    source_name=self.source_name,
                )
            else:
                results = []

            # If no ISSN match, try exact normalized name match
            if not results and query_input.normalized_name:
                results = self._search_exact_match(query_input.normalized_name)

            # Try aliases for exact matches only
            if not results:
                for alias in query_input.aliases:
                    results = self._search_exact_match(alias)
                    if results:
                        break

            if results:
                match = results[0]
                journal_id = match.get("id")

                if not journal_id or not isinstance(journal_id, int):
                    detail_logger.error(f"Invalid journal_id from match: {journal_id}")
                    raise ValueError(f"Invalid journal_id: {journal_id}")

                # Fetch retraction statistics from dedicated table
                retraction_cache = RetractionCache()
                stats = retraction_cache.get_retraction_statistics(journal_id)

                if stats:
                    total_retractions = stats.get("total_retractions", 0)
                    recent_retractions = stats.get("recent_retractions", 0)
                    very_recent_retractions = stats.get("very_recent_retractions", 0)
                    retraction_types = stats.get("retraction_types", {})
                    top_reasons = stats.get("top_reasons", [])
                    publishers = stats.get("publishers", [])
                    first_retraction_date = stats.get("first_retraction_date")
                    last_retraction_date = stats.get("last_retraction_date")
                else:
                    # No statistics found
                    total_retractions = 0
                    recent_retractions = 0
                    very_recent_retractions = 0
                    retraction_types = {}
                    top_reasons = []
                    publishers = []
                    first_retraction_date = None
                    last_retraction_date = None

                # Fetch OpenAlex publication data on-demand
                openalex_data = None
                if query_input.normalized_name:
                    openalex_data = await self._get_openalex_data_cached(
                        query_input.normalized_name, query_input.identifiers.get("issn")
                    )

                # Recalculate risk level with publication data if available
                total_publications = (
                    openalex_data.get("total_publications") if openalex_data else None
                )
                recent_publications = (
                    openalex_data.get("recent_publications") if openalex_data else None
                )

                risk_level = self._calculate_risk_level(
                    total_retractions,
                    recent_retractions,
                    total_publications,
                    recent_publications,
                )

                # Calculate retraction rates if we have publication data
                retraction_rate = None
                recent_retraction_rate = None
                if total_publications and total_publications > 0:
                    retraction_rate = (total_retractions / total_publications) * 100
                    if recent_publications and recent_publications > 0:
                        recent_retraction_rate = (
                            recent_retractions / recent_publications
                        ) * 100

                # Calculate confidence based on match quality
                confidence = self._calculate_confidence(query_input, match)

                # Prepare enriched data for result
                result_data = {
                    "total_retractions": total_retractions,
                    "recent_retractions": recent_retractions,
                    "very_recent_retractions": very_recent_retractions,
                    "risk_level": risk_level,
                    "first_retraction_date": first_retraction_date,
                    "last_retraction_date": last_retraction_date,
                    "retraction_types": retraction_types,
                    "top_reasons": top_reasons,
                    "publishers": publishers,
                    "matches": len(results),
                    "source": "Retraction Watch Database (Crossref)",
                    "source_data": match,
                    # OpenAlex publication volume data (fetched on-demand)
                    "total_publications": total_publications,
                    "recent_publications": recent_publications,
                    "recent_publications_by_year": (
                        openalex_data.get("recent_publications_by_year", {})
                        if openalex_data
                        else {}
                    ),
                    "retraction_rate": retraction_rate,  # Percentage
                    "recent_retraction_rate": recent_retraction_rate,  # Percentage
                    "openalex_id": (
                        openalex_data.get("openalex_id") if openalex_data else None
                    ),
                    "openalex_url": (
                        openalex_data.get("openalex_url") if openalex_data else None
                    ),
                    "has_publication_data": openalex_data is not None,
                }

                response_time = time.time() - start_time

                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.FOUND,
                    confidence=confidence,
                    assessment=risk_level,  # Use risk level as assessment
                    data=result_data,
                    sources=[self.source_name],
                    error_message=None,
                    response_time=response_time,
                )
            else:
                # Not found - journal has no retractions in database
                response_time = time.time() - start_time
                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.NOT_FOUND,
                    confidence=0.0,
                    assessment=None,
                    data={
                        "message": "No retractions found in Retraction Watch database",
                        "searched_in": self.source_name,
                    },
                    sources=[self.source_name],
                    error_message=None,
                    response_time=response_time,
                )

        except (
            ValueError,
            KeyError,
            OSError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as e:
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=time.time() - start_time,
            )

    async def _get_openalex_data_cached(
        self, journal_name: str, issn: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch OpenAlex data with caching (TTL: 30 days).

        Args:
            journal_name: Name of the journal
            issn: Optional ISSN for more accurate matching

        Returns:
            Dictionary with publication statistics, or None if not found
        """
        # Check cache first
        cached = self.openalex_cache.get_openalex_data(
            issn=issn, journal_name=journal_name
        )
        if cached is not None:
            detail_logger.debug(f"OpenAlex cache hit for {journal_name}")
            return cached

        # Fetch from OpenAlex API
        status_logger.info(f"Fetching OpenAlex data on-demand for: {journal_name}")
        try:
            openalex_data = await get_publication_stats(journal_name, issn)

            if openalex_data:
                # Cache successful result for 30 days
                self.openalex_cache.set_openalex_data(
                    issn=issn,
                    journal_name=journal_name,
                    openalex_data=openalex_data,
                    ttl_hours=24 * 30,
                )
                return openalex_data
            else:
                # No data found - return None without caching
                # (failures are not cached to allow retries)
                return None

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ValueError,
            KeyError,
            OSError,
        ) as e:
            status_logger.warning(
                f"Failed to fetch OpenAlex data for {journal_name}: {e}"
            )
            # Don't cache failures - allow retries
            return None

    def _search_exact_match(self, name: str) -> list[dict[str, Any]]:
        """Search for exact journal name matches only."""
        # Get all journals from this source and filter for exact matches
        all_results = self.journal_cache.search_journals(
            source_name=self.source_name, assessment=self.list_type
        )

        # Filter for exact matches (case insensitive)
        exact_matches = []
        name_lower = name.lower().strip()

        for result in all_results:
            journal_name = result.get("journal_name", "").lower().strip()
            normalized_name = result.get("normalized_name", "").lower().strip()

            # Exact match on either original or normalized name
            if journal_name == name_lower or normalized_name == name_lower:
                exact_matches.append(result)

        return exact_matches

    def _calculate_confidence(
        self, query_input: QueryInput, match: dict[str, Any]
    ) -> float:
        """Calculate confidence based on match quality - exact matches only."""

        # High confidence for exact ISSN match
        if (
            query_input.identifiers.get("issn")
            and match.get("issn") == query_input.identifiers["issn"]
        ):
            return 0.95

        # High confidence for exact name match (case insensitive)
        if query_input.normalized_name:
            query_name = query_input.normalized_name.lower().strip()
            match_name = match.get("normalized_name", "").lower().strip()
            original_name = match.get("journal_name", "").lower().strip()

            if query_name == match_name or query_name == original_name:
                return 0.90

        # If we get here, it means we have a match but it's not exact
        # This shouldn't happen with our new exact matching, so low confidence
        return 0.3

    def _calculate_risk_level(
        self,
        total: int,
        recent: int,
        total_publications: int | None = None,
        recent_publications: int | None = None,
    ) -> str:
        """
        Calculate risk level based on retraction counts and publication volumes.

        This method uses the centralized risk calculator.

        Args:
            total: Total retraction count
            recent: Recent retraction count (last 5 years)
            total_publications: Total publication count (optional)
            recent_publications: Recent publication count (optional)

        Returns:
            Risk level: 'critical', 'high', 'moderate', 'low', 'note', or 'none'
        """
        from ..risk_calculator import calculate_retraction_risk_level

        return calculate_retraction_risk_level(
            total, recent, total_publications, recent_publications
        )


# Register the backend factory
get_backend_registry().register_factory(
    "retraction_watch",
    lambda cache_ttl_hours=24: RetractionWatchBackend(cache_ttl_hours=cache_ttl_hours),
    default_config={"cache_ttl_hours": 24},
)
