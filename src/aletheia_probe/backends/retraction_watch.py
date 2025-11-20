"""Retraction Watch backend for journal quality assessment based on retraction data."""

import json
from typing import Any

from ..cache import get_cache_manager
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..openalex import get_publication_stats
from .base import CachedBackend, get_backend_registry

detail_logger = get_detail_logger()
status_logger = get_status_logger()


class RetractionWatchBackend(CachedBackend):
    """Backend that checks retraction history from Retraction Watch database."""

    def __init__(self) -> None:
        super().__init__(
            source_name="retraction_watch",
            list_type="quality_indicator",
            cache_ttl_hours=24 * 7,  # Weekly cache
        )

    def get_name(self) -> str:
        return "retraction_watch"

    def get_description(self) -> str:
        return "Checks journal retraction history from Retraction Watch database"

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Query retraction data for journal information.

        Overrides CachedBackend.query to provide custom result formatting
        with retraction-specific metadata. Fetches OpenAlex publication data
        on-demand for rate calculation.
        """
        import time

        start_time = time.time()

        try:
            # Use parent's search methods for consistency
            # Search by ISSN first (though we don't have ISSN in retraction data)
            if query_input.identifiers.get("issn"):
                results = get_cache_manager().search_journals(
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
                metadata_json = match.get("metadata")

                if metadata_json:
                    try:
                        metadata = json.loads(metadata_json)
                    except json.JSONDecodeError:
                        metadata = {}
                else:
                    metadata = {}

                total_retractions = metadata.get("total_retractions", 0)
                recent_retractions = metadata.get("recent_retractions", 0)

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
                    "very_recent_retractions": metadata.get(
                        "very_recent_retractions", 0
                    ),
                    "risk_level": risk_level,
                    "first_retraction_date": metadata.get("first_retraction_date"),
                    "last_retraction_date": metadata.get("last_retraction_date"),
                    "retraction_types": metadata.get("retraction_types", {}),
                    "top_reasons": metadata.get("top_reasons", []),
                    "publishers": metadata.get("publishers", []),
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

        except Exception as e:
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
        cache_key = f"openalex:{issn}" if issn else f"openalex:{journal_name}"

        # Check cache first
        cached = get_cache_manager().get_cached_value(cache_key)
        if cached is not None:
            detail_logger.debug(f"OpenAlex cache hit for {journal_name}")
            return json.loads(cached) if cached != "null" else None

        # Fetch from OpenAlex API
        status_logger.info(f"Fetching OpenAlex data on-demand for: {journal_name}")
        try:
            openalex_data = await get_publication_stats(journal_name, issn)

            # Cache result (including null for not found) for 30 days
            cache_value = json.dumps(openalex_data) if openalex_data else "null"
            get_cache_manager().set_cached_value(
                cache_key, cache_value, ttl_hours=24 * 30
            )

            return openalex_data

        except Exception as e:
            status_logger.warning(f"Failed to fetch OpenAlex data for {journal_name}: {e}")
            # Cache the failure for 1 day to avoid repeated API calls
            get_cache_manager().set_cached_value(cache_key, "null", ttl_hours=24)
            return None

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
    "retraction_watch", lambda: RetractionWatchBackend(), default_config={}
)
