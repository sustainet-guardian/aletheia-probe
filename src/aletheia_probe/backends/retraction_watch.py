# SPDX-License-Identifier: MIT
"""Retraction Watch backend for journal quality assessment based on retraction data."""

import asyncio
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from ..backend_exceptions import RateLimitError
from ..cache import RetractionCache
from ..confidence_utils import MatchQuality, calculate_base_confidence
from ..constants import CONFIDENCE_THRESHOLD_LOW
from ..enums import AssessmentType, EvidenceType, RiskLevel
from ..fallback_chain import FallbackStrategy, QueryFallbackChain
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..openalex import get_publication_stats
from ..risk_calculator import calculate_retraction_risk_level
from .base import ApiBackendWithCache, get_backend_registry
from .protocols import DataSyncCapable


if TYPE_CHECKING:
    from ..updater.core import DataSource
    from ..updater.sources.retraction_watch import RetractionWatchSource


detail_logger = get_detail_logger()
status_logger = get_status_logger()


def _risk_level_to_assessment(risk_level: RiskLevel) -> AssessmentType:
    """Convert risk level to assessment type.

    Args:
        risk_level: Risk level from retraction analysis (RiskLevel enum)

    Returns:
        Corresponding assessment type
    """
    mapping = {
        RiskLevel.NONE: AssessmentType.LEGITIMATE,
        RiskLevel.NOTE: AssessmentType.LEGITIMATE,
        RiskLevel.LOW: AssessmentType.SUSPICIOUS,
        RiskLevel.MODERATE: AssessmentType.PREDATORY,
        RiskLevel.HIGH: AssessmentType.PREDATORY,
        RiskLevel.CRITICAL: AssessmentType.PREDATORY,
    }
    return mapping.get(risk_level, AssessmentType.UNKNOWN)


class RetractionWatchBackend(ApiBackendWithCache, DataSyncCapable):
    """Backend that checks retraction history from Retraction Watch database.

    This backend implements both ApiBackendWithCache patterns (cache-first queries with
    API fallback) and DataSyncCapable protocol (local data synchronization from
    external sources). It needs local retraction statistics data to function
    properly, which is synced from the Retraction Watch GitLab repository.
    """

    def __init__(self, cache_ttl_hours: int = 24) -> None:
        """Initialize backend with configurable cache TTL.

        Args:
            cache_ttl_hours: Cache time-to-live in hours (default: 24)
        """
        super().__init__(cache_ttl_hours=cache_ttl_hours)
        self.list_type = "quality_indicator"
        self._data_source: RetractionWatchSource | None = None

    def get_name(self) -> str:
        return "retraction_watch"

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type for retraction data."""
        return EvidenceType.QUALITY_INDICATOR

    # DataSyncCapable protocol implementation
    @property
    def source_name(self) -> str:
        """Name of the data source for synchronization."""
        return "retraction_watch"

    def get_data_source(self) -> "DataSource | None":
        """Get the RetractionWatchSource instance for data synchronization."""
        if self._data_source is None:
            from ..updater.sources.retraction_watch import RetractionWatchSource

            self._data_source = RetractionWatchSource()
        return self._data_source

    def needs_sync(self) -> bool:
        """Check if retraction statistics data needs synchronization.

        Returns True if the retraction_statistics table is empty or
        data appears to be missing.
        """
        try:
            retraction_cache = RetractionCache()
            # Check if we have any retraction statistics by querying a simple journal
            # If the cache returns None for a basic query, we likely need sync
            test_result = retraction_cache.get_retraction_statistics(1)
            # If we get None but the cache exists, the table is probably empty
            return test_result is None
        except Exception as e:
            detail_logger.warning(f"Error checking retraction statistics: {e}")
            # If we can't check, assume we need sync
            return True

    def _search_retraction_data(
        self, query_input: QueryInput, chain: QueryFallbackChain
    ) -> list[dict[str, Any]]:
        """Search for retraction data using various query strategies.

        Args:
            query_input: Normalized query input with journal information
            chain: Fallback chain to log attempts

        Returns:
            List of matching journal records from the database
        """
        detail_logger.debug("RetractionWatch._search_retraction_data called")

        # Search by ISSN first (though we don't have ISSN in retraction data)
        detail_logger.debug("RetractionWatch._search_retraction_data try issn search")
        results = []
        if query_input.identifiers.get("issn"):
            results = self.journal_cache.search_journals(
                issn=query_input.identifiers["issn"],
                source_name=self.source_name,
            )
            chain.log_attempt(
                FallbackStrategy.ISSN,
                success=len(results) > 0,
                query_value=query_input.identifiers["issn"],
            )

        # If no ISSN match, try exact normalized name match
        detail_logger.debug(
            "RetractionWatch._search_retraction_data try normalized name"
        )
        if not results and query_input.normalized_name:
            results = self._search_exact_match(query_input.normalized_name)
            chain.log_attempt(
                FallbackStrategy.EXACT_NAME,
                success=len(results) > 0,
                query_value=query_input.normalized_name,
            )

        # Try aliases for exact matches only
        detail_logger.debug(
            "RetractionWatch._search_retraction_data try search exact match"
        )
        if not results:
            for alias in query_input.aliases:
                results = self._search_exact_match(alias)
                chain.log_attempt(
                    FallbackStrategy.EXACT_ALIASES,
                    success=len(results) > 0,
                    query_value=alias,
                )
                if results:
                    break

        detail_logger.debug(
            f"RetractionWatch._search_retraction_data: results {len(results) if results else None}"
        )
        return results

    def _handle_not_found(
        self, start_time: float, chain: QueryFallbackChain
    ) -> BackendResult:
        """Handle the case when no retraction data is found for a journal.

        Args:
            start_time: Query start time for response time calculation
            chain: Fallback chain used for this query

        Returns:
            BackendResult indicating no data was found
        """
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
            fallback_chain=chain,
        )

    async def _build_result_data(
        self,
        query_input: QueryInput,
        match: dict[str, Any],
        start_time: float,
        chain: QueryFallbackChain,
    ) -> BackendResult:
        """Build comprehensive result data from retraction and publication statistics.

        Args:
            query_input: Original query input
            match: Matching journal record from database
            start_time: Query start time for response time calculation
            chain: Fallback chain used for this query

        Returns:
            BackendResult with comprehensive retraction assessment
        """
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

        risk_level = calculate_retraction_risk_level(
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
            "matches": 1,  # Single match from search
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
            assessment=_risk_level_to_assessment(risk_level),
            data=result_data,
            sources=[self.source_name],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query retraction data for journal information.

        This method orchestrates the query process by delegating to specialized methods.
        Results are automatically cached by the ApiBackendWithCache parent.

        Args:
            query_input: Normalized query input with journal information

        Returns:
            BackendResult with retraction assessment and metadata
        """
        detail_logger.debug("RetractionWatch._query_api called")
        start_time = time.time()
        chain = QueryFallbackChain(
            [
                FallbackStrategy.ISSN,
                FallbackStrategy.EXACT_NAME,
                FallbackStrategy.EXACT_ALIASES,
            ]
        )

        try:
            # Search for retraction data using multiple strategies
            results = self._search_retraction_data(query_input, chain)

            if results:
                # Found data - build comprehensive result
                match = results[0]
                return await self._build_result_data(
                    query_input, match, start_time, chain
                )
            else:
                # No data found - return not found result
                return self._handle_not_found(start_time, chain)

        except Exception as e:
            status_logger.error(f"RetractionWatch API error: {e}")
            return self._build_error_result(e, time.time() - start_time, chain)

    def _build_error_result(
        self,
        exception: Exception,
        response_time: float,
        chain: QueryFallbackChain | None = None,
    ) -> BackendResult:
        """Create a standardized error BackendResult from an exception.

        Args:
            exception: The exception that occurred
            response_time: Time taken before error occurred
            chain: Fallback chain used (optional)

        Returns:
            BackendResult with appropriate status and error message
        """
        status = self._map_exception_to_backend_status(exception)
        return BackendResult(
            backend_name=self.get_name(),
            status=status,
            confidence=0.0,
            assessment=None,
            error_message=str(exception),
            response_time=response_time,
            cached=False,
            fallback_chain=chain or QueryFallbackChain([]),
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
            RateLimitError,
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
        """Search for exact journal name matches using database-level filtering."""
        return self.journal_cache.search_journals_by_name(
            name=name,
            source_name=self.source_name,
            assessment=self.list_type,
        )

    def _calculate_confidence(
        self, query_input: QueryInput, match: dict[str, Any]
    ) -> float:
        """Calculate confidence based on match quality - exact matches only."""

        # High confidence for exact ISSN match
        if (
            query_input.identifiers.get("issn")
            and match.get("issn") == query_input.identifiers["issn"]
        ):
            return calculate_base_confidence(MatchQuality.EXACT_ISSN)

        # High confidence for exact name match (case insensitive)
        if query_input.normalized_name:
            query_name = query_input.normalized_name.lower().strip()
            match_name = match.get("normalized_name", "").lower().strip()
            original_name = match.get("journal_name", "").lower().strip()

            if query_name == match_name or query_name == original_name:
                return calculate_base_confidence(MatchQuality.EXACT_NAME)

        # If we get here, it means we have a match but it's not exact
        # This shouldn't happen with our new exact matching, so low confidence
        return CONFIDENCE_THRESHOLD_LOW


# Register the backend factory
get_backend_registry().register_factory(
    "retraction_watch",
    lambda cache_ttl_hours=24: RetractionWatchBackend(cache_ttl_hours=cache_ttl_hours),
    default_config={"cache_ttl_hours": 24},
)
