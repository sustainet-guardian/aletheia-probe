# SPDX-License-Identifier: MIT
"""OpenAlex backend with pattern analysis for predatory journal detection."""

from datetime import datetime
from typing import Any

from ..constants import CONFIDENCE_THRESHOLD_LOW
from ..enums import AssessmentType, EvidenceType
from ..fallback_chain import FallbackStrategy, QueryFallbackChain
from ..fallback_executor import automatic_fallback
from ..logging_config import get_detail_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..openalex import OpenAlexClient
from ..validation import validate_email
from .base import ApiBackendWithCache, get_backend_registry
from .fallback_mixin import FallbackStrategyMixin


# OpenAlex pattern analysis constants
CITATION_RATIO_SUSPICIOUS: int = 10
GROWTH_RATE_THRESHOLD: float = 0.5
MIN_PUBLICATION_VOLUME: int = 100


class OpenAlexAnalyzerBackend(ApiBackendWithCache, FallbackStrategyMixin):
    """Backend that analyzes OpenAlex data patterns to assess journal legitimacy."""

    def __init__(
        self, email: str = "noreply@aletheia-probe.org", cache_ttl_hours: int = 24
    ):
        """Initialize OpenAlex analyzer backend.

        Args:
            email: Email for OpenAlex polite pool access
            cache_ttl_hours: Cache TTL in hours

        Raises:
            TypeError: If email is not a string
            ValueError: If email format is invalid
        """
        super().__init__(cache_ttl_hours)
        self.email = validate_email(email)
        self.detail_logger = get_detail_logger()

    def get_name(self) -> str:
        """Return backend name."""
        return "openalex_analyzer"

    def get_evidence_type(self) -> EvidenceType:
        """Return evidence type."""
        return EvidenceType.HEURISTIC

    @automatic_fallback(
        [
            FallbackStrategy.NORMALIZED_NAME,
            FallbackStrategy.ISSN,
            FallbackStrategy.ALIASES,
            FallbackStrategy.ACRONYMS,
        ]
    )
    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query OpenAlex API and analyze patterns using automatic fallback chain."""
        self.detail_logger.info(
            f"OpenAlex: Starting query for '{query_input.raw_input}'"
        )
        # Decorator handles all execution logic
        # This line will never be reached as the decorator intercepts the call
        raise NotImplementedError(
            "This should be handled by @automatic_fallback decorator"
        )

    # FallbackStrategyMixin required methods
    async def _search_by_issn(self, issn: str) -> dict[str, Any] | None:
        """Search OpenAlex by ISSN/eISSN identifier.

        Args:
            issn: ISSN or eISSN identifier to search for

        Returns:
            OpenAlex data if found, None if no match
        """
        self.detail_logger.debug(f"OpenAlex: Searching by ISSN {issn}")
        async with OpenAlexClient(email=self.email) as client:
            # OpenAlex client requires journal_name, so use empty string for ISSN-only searches
            return await client.enrich_journal_data(
                journal_name="", issn=issn, eissn=None
            )

    async def _search_by_name(
        self, name: str, exact: bool = True
    ) -> dict[str, Any] | None:
        """Search OpenAlex by journal name.

        Args:
            name: Journal name to search for
            exact: Whether to use exact matching (not implemented differently in OpenAlex)

        Returns:
            OpenAlex data if found, None if no match
        """
        self.detail_logger.debug(f"OpenAlex: Searching by name '{name}'")
        async with OpenAlexClient(email=self.email) as client:
            return await client.enrich_journal_data(
                journal_name=name, issn=None, eissn=None
            )

    async def handle_acronyms_strategy(self, query_input: QueryInput) -> Any | None:
        """OpenAlex-specific acronyms strategy implementation.

        OpenAlex supports acronym expansion, so we try to search with acronyms.

        Args:
            query_input: Query input with potential acronyms

        Returns:
            OpenAlex data if found, None if no match
        """
        # OpenAlex doesn't have special acronym handling in the client,
        # but we can try searching with the raw input if it looks like an acronym
        raw_input = query_input.raw_input
        if raw_input and len(raw_input) <= 10 and raw_input.isupper():
            # Looks like an acronym
            self.detail_logger.debug(f"OpenAlex: Searching for acronym '{raw_input}'")
            return await self._search_by_name(raw_input, exact=True)
        return None

    async def _search_with_aliases(
        self,
        client: OpenAlexClient,
        query_input: QueryInput,
        journal_name: str,
        issn: str | None,
        eissn: str | None,
        chain: QueryFallbackChain,
    ) -> dict[str, Any] | None:
        """Search for journal data using aliases when primary search fails.

        Args:
            client: OpenAlex client instance
            query_input: Query input containing aliases
            journal_name: Primary journal name that failed
            issn: ISSN identifier
            eissn: eISSN identifier
            chain: Fallback chain to log attempts

        Returns:
            OpenAlex data if found using aliases, None otherwise
        """
        if not query_input.aliases:
            return None

        self.detail_logger.info(
            f"OpenAlex: Normalized name '{journal_name}' not found, trying {len(query_input.aliases)} alias(es)"
        )

        for alias in query_input.aliases:
            openalex_data = await client.enrich_journal_data(
                journal_name=alias, issn=issn, eissn=eissn
            )
            chain.log_attempt(
                FallbackStrategy.ALIASES,
                success=openalex_data is not None,
                query_value=alias,
            )
            if openalex_data:
                self.detail_logger.info(f"OpenAlex: Found match using alias '{alias}'")
                return openalex_data

        return None

    def _build_not_found_result_with_chain(
        self,
        query_input: QueryInput,
        chain: QueryFallbackChain,
        response_time: float,
    ) -> BackendResult:
        """Build BackendResult for when journal is not found in OpenAlex.

        Args:
            query_input: Original query input
            chain: Fallback chain used for this query
            response_time: Time taken for the query

        Returns:
            BackendResult with NOT_FOUND status
        """
        journal_name = query_input.normalized_name or query_input.raw_input
        issn = query_input.identifiers.get("issn")
        eissn = query_input.identifiers.get("eissn")

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={
                "searched_for": journal_name,
                "issn": issn,
                "eissn": eissn,
                "aliases_tried": query_input.aliases,
            },
            sources=["https://api.openalex.org"],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )

    def _build_success_result_with_chain(
        self,
        openalex_data: dict[str, Any],
        query_input: QueryInput,
        chain: QueryFallbackChain,
        response_time: float,
    ) -> BackendResult:
        """Build BackendResult for successful OpenAlex query.

        Args:
            openalex_data: Raw data from OpenAlex API
            query_input: Original query input
            response_time: Time taken for the query
            chain: Fallback chain used for this query

        Returns:
            BackendResult with FOUND status and analysis
        """
        # Store acronym mapping if display_name contains acronym in parentheses
        self._store_acronym_from_openalex(openalex_data, query_input)

        # Route to appropriate assessment based on publication type
        source_type = openalex_data.get("source_type", "").lower()
        display_name = openalex_data.get("display_name", "").lower()

        # Override OpenAlex misclassification if display_name suggests conference
        # OpenAlex sometimes incorrectly classifies conference proceedings as journals
        # Detect conferences by common keywords in the display name
        conference_keywords = [
            "proceedings",
            "conference",
            "symposium",
            "workshop",
        ]
        if source_type != "conference" and any(
            keyword in display_name for keyword in conference_keywords
        ):
            self.detail_logger.info(
                f"OpenAlex: Overriding source_type '{source_type}' to 'conference' "
                f"based on display_name: '{openalex_data.get('display_name')}'"
            )
            source_type = "conference"

        if source_type == "conference":
            analysis = self._analyze_conference_patterns(openalex_data)
        else:
            # Default to journal analysis for journals and unknown types
            analysis = self._analyze_journal_patterns(openalex_data)

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.FOUND,
            confidence=analysis["confidence"],
            assessment=analysis["assessment"],
            data={
                "openalex_data": openalex_data,
                "analysis": analysis,
                "metrics": analysis["metrics"],
                "red_flags": analysis["red_flags"],
                "green_flags": analysis["green_flags"],
                "publication_type": source_type
                or "journal",  # Use corrected source_type
            },
            sources=[
                "https://api.openalex.org",
                openalex_data.get("openalex_url", ""),
            ],
            error_message=None,
            response_time=response_time,
            fallback_chain=chain,
        )

    def _build_error_result(
        self,
        exception: Exception,
        response_time: float,
        chain: QueryFallbackChain | None = None,
    ) -> BackendResult:
        """Build error result with populated fallback chain.

        Args:
            exception: Exception that occurred during query
            response_time: Query response time
            chain: Fallback chain with logged attempts

        Returns:
            Error BackendResult
        """
        self.detail_logger.error(f"OpenAlex API error: {exception}")

        return BackendResult(
            backend_name=self.get_name(),
            status=BackendStatus.ERROR,
            confidence=0.0,
            assessment=None,
            data={"error_details": str(exception)},
            sources=["https://api.openalex.org"],
            error_message=str(exception),
            response_time=response_time,
            fallback_chain=chain or QueryFallbackChain([]),
        )

    def _store_acronym_from_openalex(
        self, openalex_data: dict[str, Any], query_input: QueryInput
    ) -> None:
        """Extract and store acronym mapping from OpenAlex display_name.

        OpenAlex sometimes includes acronyms in parentheses in the display_name field.
        For example: "International Conference on Machine Learning (ICML)"

        Args:
            openalex_data: Raw data from OpenAlex API
            query_input: Query input containing venue type information
        """
        from ..cache import AcronymCache
        from ..normalizer import InputNormalizer

        display_name = openalex_data.get("display_name")
        if not display_name:
            return

        # Use the normalizer's acronym extraction logic
        normalizer = InputNormalizer()
        acronyms = normalizer._extract_acronyms(display_name)

        if acronyms:
            # Extract acronym mappings
            mappings = normalizer._extract_acronym_mappings_from_text(
                display_name, acronyms
            )

            # Store original venue type value - filtering can be done during reading
            entity_type = query_input.venue_type.value

            # Store each mapping in the cache
            acronym_cache = AcronymCache()
            for acronym, full_name in mappings.items():
                acronym_cache.store_acronym_mapping(
                    acronym, full_name, entity_type, source="openalex_response"
                )

    def _analyze_journal_patterns(
        self, openalex_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyze journal publication patterns to detect predatory characteristics.

        Args:
            openalex_data: Raw data from OpenAlex

        Returns:
            Analysis dictionary with assessment, confidence, and flags
        """
        # Calculate shared base metrics
        metrics = self._calculate_base_metrics(openalex_data)

        # Check for journal-specific green flags (legitimacy indicators)
        green_flags = self._check_journal_green_flags(metrics)

        # Check for journal-specific red flags (predatory indicators)
        red_flags = self._check_journal_red_flags(metrics)

        # Determine final assessment and confidence
        assessment, confidence = self._determine_assessment(
            red_flags, green_flags, metrics
        )

        return {
            "assessment": assessment,
            "confidence": confidence,
            "metrics": metrics,
            "red_flags": red_flags,
            "green_flags": green_flags,
            "reasoning": self._generate_reasoning(red_flags, green_flags, metrics),
        }

    def _analyze_conference_patterns(
        self, openalex_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyze conference publication patterns to detect predatory characteristics.

        Args:
            openalex_data: Raw data from OpenAlex

        Returns:
            Analysis dictionary with assessment, confidence, and flags
        """
        # Calculate shared base metrics
        metrics = self._calculate_base_metrics(openalex_data)

        # Check for conference-specific green flags (legitimacy indicators)
        green_flags = self._check_conference_green_flags(metrics)

        # Check for conference-specific red flags (predatory indicators)
        red_flags = self._check_conference_red_flags(metrics)

        # Determine final assessment and confidence
        assessment, confidence = self._determine_assessment(
            red_flags, green_flags, metrics
        )

        return {
            "assessment": assessment,
            "confidence": confidence,
            "metrics": metrics,
            "red_flags": red_flags,
            "green_flags": green_flags,
            "reasoning": self._generate_reasoning(red_flags, green_flags, metrics),
        }

    def _calculate_base_metrics(self, openalex_data: dict[str, Any]) -> dict[str, Any]:
        """Calculate base metrics shared by both journals and conferences.

        Args:
            openalex_data: Raw data from OpenAlex

        Returns:
            Dictionary of calculated metrics
        """
        # Extract key metrics
        total_publications = openalex_data.get("total_publications", 0)
        total_citations = openalex_data.get("cited_by_count", 0)
        first_year = openalex_data.get("first_publication_year")
        last_year = openalex_data.get("last_publication_year")
        recent_publications = openalex_data.get("recent_publications", 0)
        is_in_doaj = openalex_data.get("is_in_doaj", False)

        current_year = datetime.now().year

        # Calculate derived metrics
        years_active = (
            max(1, (last_year or current_year) - (first_year or current_year) + 1)
            if first_year
            else 1
        )
        publication_rate_per_year = (
            total_publications / years_active if years_active > 0 else 0
        )
        citation_ratio = (
            total_citations / total_publications if total_publications > 0 else 0
        )

        # Recent activity assessment (last 5 years)
        recent_years = 5
        recent_rate_per_year = (
            recent_publications / recent_years if recent_years > 0 else 0
        )

        return {
            "total_publications": total_publications,
            "total_citations": total_citations,
            "years_active": years_active,
            "publication_rate_per_year": publication_rate_per_year,
            "citation_ratio": citation_ratio,
            "recent_publications": recent_publications,
            "recent_rate_per_year": recent_rate_per_year,
            "first_year": first_year,
            "last_year": last_year,
            "is_in_doaj": is_in_doaj,
            "current_year": current_year,
            "source_type": openalex_data.get("source_type"),
        }

    def _check_journal_green_flags(self, metrics: dict[str, Any]) -> list[str]:
        """Check for green flags specific to journal legitimacy.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            List of green flag descriptions
        """
        green_flags = []

        citation_ratio = metrics["citation_ratio"]
        years_active = metrics["years_active"]
        total_publications = metrics["total_publications"]
        publication_rate_per_year = metrics["publication_rate_per_year"]
        is_in_doaj = metrics["is_in_doaj"]
        recent_publications = metrics["recent_publications"]
        last_year = metrics["last_year"]
        current_year = metrics["current_year"]

        # Strong citation ratio suggests quality content
        if citation_ratio >= CITATION_RATIO_SUSPICIOUS:
            green_flags.append(
                f"High citation ratio: {citation_ratio:.1f} citations per paper"
            )
        elif citation_ratio >= 3:
            green_flags.append(
                f"Good citation ratio: {citation_ratio:.1f} citations per paper"
            )

        # Established journal with long publication history
        if years_active >= 20 and total_publications >= 1000:
            green_flags.append(
                f"Well-established journal: {years_active} years active with {total_publications} papers"
            )
        elif years_active >= 10 and total_publications >= 500:
            green_flags.append(
                f"Established journal: {years_active} years active with {total_publications} papers"
            )

        # Realistic publication rate for established journals
        if 20 <= publication_rate_per_year <= 500:
            green_flags.append(
                f"Realistic publication rate: {publication_rate_per_year:.0f} papers/year"
            )

        # Listed in DOAJ (already verified elsewhere, but supports legitimacy)
        if is_in_doaj:
            green_flags.append("Listed in Directory of Open Access Journals (DOAJ)")

        # Consistent recent activity (journals should publish regularly)
        if recent_publications > 0 and last_year and last_year >= current_year - 2:
            green_flags.append(
                f"Recently active: {recent_publications} papers in last 5 years"
            )

        return green_flags

    def _check_journal_red_flags(self, metrics: dict[str, Any]) -> list[str]:
        """Check for red flags specific to journal predatory behavior.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            List of red flag descriptions
        """
        red_flags = []

        citation_ratio = metrics["citation_ratio"]
        years_active = metrics["years_active"]
        total_publications = metrics["total_publications"]
        publication_rate_per_year = metrics["publication_rate_per_year"]
        recent_publications = metrics["recent_publications"]
        recent_rate_per_year = metrics["recent_rate_per_year"]
        last_year = metrics["last_year"]
        current_year = metrics["current_year"]

        # Publication mill pattern - extremely high volume
        if publication_rate_per_year > 1000:
            red_flags.append(
                f"Publication mill pattern: {publication_rate_per_year:.0f} papers/year (suspicious volume)"
            )
        elif publication_rate_per_year > 500:
            red_flags.append(
                f"Very high publication rate: {publication_rate_per_year:.0f} papers/year"
            )

        # Very low citation ratio suggests poor quality
        if citation_ratio < GROWTH_RATE_THRESHOLD and total_publications >= 50:
            red_flags.append(
                f"Very low citation ratio: {citation_ratio:.2f} citations per paper"
            )
        elif citation_ratio < 1.0 and total_publications >= MIN_PUBLICATION_VOLUME:
            red_flags.append(
                f"Low citation ratio: {citation_ratio:.2f} citations per paper"
            )

        # New journal with suspiciously high output
        if years_active <= 3 and publication_rate_per_year > 200:
            red_flags.append(
                f"New journal with high output: {publication_rate_per_year:.0f} papers/year in only {years_active} years"
            )

        # Recent explosion in publication volume (possible takeover or transformation)
        if recent_publications > 0 and years_active > 5:
            historical_rate = (total_publications - recent_publications) / max(
                1, years_active - 5
            )
            if (
                recent_rate_per_year > historical_rate * 3
                and recent_rate_per_year > 100
            ):
                red_flags.append(
                    f"Recent publication explosion: {recent_rate_per_year:.0f} recent vs {historical_rate:.0f} historical papers/year"
                )

        # Journal appears inactive (journals should publish regularly)
        if last_year and last_year < current_year - 3:
            red_flags.append(
                f"Journal appears inactive: last publication in {last_year}"
            )

        # Very new journal with minimal track record
        if years_active <= 2 and total_publications < 20:
            red_flags.append(
                f"Very new journal: only {years_active} years active with {total_publications} papers"
            )

        return red_flags

    def _check_conference_green_flags(self, metrics: dict[str, Any]) -> list[str]:
        """Check for green flags specific to conference legitimacy.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            List of green flag descriptions
        """
        green_flags = []

        citation_ratio = metrics["citation_ratio"]
        total_publications = metrics["total_publications"]
        total_citations = metrics["total_citations"]
        last_year = metrics["last_year"]
        current_year = metrics["current_year"]

        # Strong citation ratio for conferences (conferences often have higher ratios)
        if citation_ratio >= 50:
            green_flags.append(
                f"Excellent citation ratio: {citation_ratio:.1f} citations per paper"
            )
        elif citation_ratio >= 20:
            green_flags.append(
                f"Good citation ratio: {citation_ratio:.1f} citations per paper"
            )

        # High total citations indicate impact
        if total_citations > 100000:
            green_flags.append(
                f"High-impact venue: {total_citations:,} total citations"
            )
        elif total_citations > 20000:
            green_flags.append(
                f"Significant impact: {total_citations:,} total citations"
            )

        # Substantial proceedings volume
        if total_publications > 1000:
            green_flags.append(
                f"Major venue: {total_publications:,} total publications"
            )
        elif total_publications > 100:
            green_flags.append(
                f"Established venue: {total_publications:,} total publications"
            )

        # Recent activity (conferences may have gaps)
        if last_year and last_year >= current_year - 5:
            green_flags.append(f"Recently active: last publication in {last_year}")

        return green_flags

    def _check_conference_red_flags(self, metrics: dict[str, Any]) -> list[str]:
        """Check for red flags specific to conference predatory behavior.

        Args:
            metrics: Dictionary of calculated metrics

        Returns:
            List of red flag descriptions
        """
        red_flags = []

        citation_ratio = metrics["citation_ratio"]
        years_active = metrics["years_active"]
        total_publications = metrics["total_publications"]
        publication_rate_per_year = metrics["publication_rate_per_year"]
        last_year = metrics["last_year"]
        current_year = metrics["current_year"]

        # Extremely low citation ratio (even for conferences)
        if citation_ratio < 0.5 and total_publications >= 50:
            red_flags.append(
                f"Very low citation ratio: {citation_ratio:.2f} citations per paper"
            )

        # Conference appears completely discontinued
        if last_year and last_year < current_year - 15:
            red_flags.append(
                f"Conference appears discontinued: last publication in {last_year}"
            )

        # Suspiciously high publication volume for a conference
        if publication_rate_per_year > 5000:
            red_flags.append(
                f"Suspicious volume for conference: {publication_rate_per_year:.0f} papers/year"
            )

        # Conference with virtually no content
        if total_publications < 5 and years_active > 2:
            red_flags.append(
                f"Minimal content: only {total_publications} papers over {years_active} years"
            )

        return red_flags

    def _determine_assessment(
        self, red_flags: list[str], green_flags: list[str], metrics: dict[str, Any]
    ) -> tuple[AssessmentType | None, float]:
        """Determine final assessment and confidence based on flags.

        Args:
            red_flags: List of red flag descriptions
            green_flags: List of green flag descriptions
            metrics: Dictionary of calculated metrics

        Returns:
            Tuple of (assessment, confidence)
        """
        red_flag_weight = len(red_flags)
        green_flag_weight = len(green_flags)

        # Debug output to see actual values
        self.detail_logger.info(
            f"OpenAlex: citation_ratio={metrics['citation_ratio']}, years_active={metrics['years_active']}, total_publications={metrics['total_publications']}, red_flags={red_flag_weight}, green_flags={green_flag_weight}"
        )

        # First check for strong override cases
        override_result = self._check_override_assessments(
            red_flag_weight, green_flag_weight, metrics
        )
        if override_result:
            return override_result

        # Calculate assessment based on flag counts
        return self._calculate_flag_based_assessment(red_flag_weight, green_flag_weight)

    def _check_override_assessments(
        self,
        red_flag_weight: int,
        green_flag_weight: int,
        metrics: dict[str, Any],
    ) -> tuple[AssessmentType, float] | None:
        """Check for special case assessments that override general flag logic.

        Args:
            red_flag_weight: Number of red flags
            green_flag_weight: Number of green flags
            metrics: Dictionary of calculated metrics

        Returns:
            (assessment, confidence) tuple if override applies, None otherwise
        """
        citation_ratio = metrics["citation_ratio"]
        years_active = metrics["years_active"]
        total_publications = metrics["total_publications"]
        publication_rate_per_year = metrics["publication_rate_per_year"]

        # Strong legitimacy signals
        if citation_ratio >= 10 and years_active >= 20 and total_publications >= 1000:
            # Well-established journal with strong citations should be legitimate
            # even if it has high publication rates (e.g., conference proceedings)
            self.detail_logger.info(
                "OpenAlex: LEGITIMATE override triggered! Metrics passed hierarchical thresholds"
            )
            confidence = min(0.85, 0.75 + (green_flag_weight * 0.03))
            return AssessmentType.LEGITIMATE, confidence
        elif citation_ratio >= 20 and years_active >= 10:
            # Exceptionally high citation ratio with decent history
            return AssessmentType.LEGITIMATE, 0.90

        # Strong predatory signals
        if publication_rate_per_year > 2000 or (
            citation_ratio < 0.2 and total_publications >= MIN_PUBLICATION_VOLUME
        ):
            confidence = max(0.90, min(0.95, 0.85 + (red_flag_weight * 0.02)))
            return AssessmentType.PREDATORY, confidence

        return None

    def _calculate_flag_based_assessment(
        self, red_flag_weight: int, green_flag_weight: int
    ) -> tuple[AssessmentType | None, float]:
        """Calculate assessment and confidence based on flag counts.

        Args:
            red_flag_weight: Number of red flags
            green_flag_weight: Number of green flags

        Returns:
            Tuple of (assessment, confidence)
        """
        if red_flag_weight >= 2 and green_flag_weight >= 3:
            # Mixed signals but strong green flags should win
            return AssessmentType.LEGITIMATE, 0.65
        elif red_flag_weight >= 2:
            # Multiple red flags suggest predatory
            if red_flag_weight >= 3:
                confidence = min(0.85, 0.60 + (red_flag_weight - 2) * 0.05)
                return AssessmentType.PREDATORY, confidence
            else:
                return AssessmentType.PREDATORY, 0.65
        elif green_flag_weight >= 2:
            # Multiple green flags suggest legitimate
            if green_flag_weight >= 3:
                confidence = min(0.90, 0.70 + (green_flag_weight - 2) * 0.05)
                return AssessmentType.LEGITIMATE, confidence
            else:
                return AssessmentType.LEGITIMATE, 0.75
        elif red_flag_weight == 1 and green_flag_weight == 0:
            # Single red flag, no green flags
            return AssessmentType.PREDATORY, 0.55
        elif green_flag_weight == 1 and red_flag_weight == 0:
            # Single green flag, no red flags
            return AssessmentType.LEGITIMATE, 0.60
        else:
            # Mixed signals or insufficient data
            return None, CONFIDENCE_THRESHOLD_LOW

    def _generate_reasoning(
        self, red_flags: list[str], green_flags: list[str], metrics: dict[str, Any]
    ) -> list[str]:
        """Generate human-readable reasoning for the assessment."""
        reasoning = []

        if green_flags:
            reasoning.append("Positive indicators:")
            reasoning.extend([f"  • {flag}" for flag in green_flags])

        if red_flags:
            reasoning.append("Warning signs:")
            reasoning.extend([f"  • {flag}" for flag in red_flags])

        # Add summary statistics
        reasoning.append(
            f"Journal statistics: {metrics['total_publications']} papers over {metrics['years_active']} years"
        )
        reasoning.append(
            f"Citation metrics: {metrics['citation_ratio']:.2f} citations per paper on average"
        )

        if not green_flags and not red_flags:
            reasoning.append("Mixed or insufficient signals for clear assessment")

        return reasoning


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "openalex_analyzer",
    lambda email="noreply@aletheia-probe.org",
    cache_ttl_hours=24: OpenAlexAnalyzerBackend(
        email=email, cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"email": "noreply@aletheia-probe.org", "cache_ttl_hours": 24},
)
