# SPDX-License-Identifier: MIT
"""Query dispatcher for orchestrating backend assessment requests."""

import asyncio
import time
from typing import Any

from .backends.base import Backend, get_backend_registry
from .config import get_config_manager
from .constants import (
    AGREEMENT_BONUS_AMOUNT,
    CONFIDENCE_THRESHOLD_HIGH,
)
from .enums import AssessmentType, EvidenceType
from .logging_config import get_detail_logger, get_status_logger
from .models import AssessmentResult, BackendResult, BackendStatus, QueryInput


class QueryDispatcher:
    """Orchestrates queries to multiple backends and aggregates results.

    The QueryDispatcher is the central component for journal assessment. It:
    - Coordinates queries across multiple data sources (backends)
    - Aggregates results using weighted voting
    - Applies heuristics and agreement bonuses
    - Returns a consolidated assessment with confidence scores

    Examples:
        Basic usage:
        >>> import asyncio
        >>> from aletheia_probe import query_dispatcher
        >>> from aletheia_probe.models import QueryInput
        >>>
        >>> async def assess():
        ...     query = QueryInput(
        ...         raw_input="Nature Communications",
        ...         normalized_name="nature communications",
        ...         issn="2041-1723"
        ...     )
        ...     result = await query_dispatcher.assess_journal(query)
        ...     print(f"Classification: {result.assessment}")
        ...     print(f"Confidence: {result.confidence:.0%}")
        ...     return result
        >>>
        >>> asyncio.run(assess())

        Processing the result:
        >>> result = await query_dispatcher.assess_journal(query)
        >>> if result.assessment == AssessmentType.PREDATORY:
        ...     print("Warning: This journal may be predatory")
        ...     for backend in result.backend_results:
        ...         print(f"  {backend.backend_name}: {backend.assessment}")
    """

    def __init__(self) -> None:
        self.config_manager = get_config_manager()
        self.config = self.config_manager.load_config()
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    async def assess_journal(self, query_input: QueryInput) -> AssessmentResult:
        """Assess a journal using all enabled backends.

        Args:
            query_input: Normalized query input

        Returns:
            AssessmentResult with aggregated assessment from all backends
        """
        start_time = time.time()

        # Get enabled backends from registry
        enabled_backends = self._get_enabled_backends()

        self.detail_logger.info(
            f"Dispatcher: Found {len(enabled_backends)} enabled backends: {[b.get_name() for b in enabled_backends]}"
        )
        self.detail_logger.info(f"Dispatcher: Assessing query: {query_input.raw_input}")

        if not enabled_backends:
            self.status_logger.warning("No enabled backends found")
            return AssessmentResult(
                input_query=query_input.raw_input,
                assessment=AssessmentType.UNKNOWN,
                confidence=0.0,
                overall_score=0.0,
                backend_results=[],
                metadata=None,
                reasoning=["No backends available for assessment"],
                processing_time=time.time() - start_time,
            )

        self.status_logger.info(
            f"Querying {len(enabled_backends)} backends for: {query_input.raw_input}"
        )

        # Query all backends concurrently
        backend_results = await self._query_backends(enabled_backends, query_input)

        # Calculate final assessment using simple heuristics
        assessment_result = self._calculate_assessment(
            query_input, backend_results, time.time() - start_time
        )

        return assessment_result

    def _get_enabled_backends(self) -> list[Backend]:
        """Get list of enabled and configured backends."""
        enabled_backends: list[Backend] = []
        enabled_names = self.config_manager.get_enabled_backends()
        backend_registry = get_backend_registry()

        # If no backends configured, use all available
        if not enabled_names:
            enabled_names = backend_registry.get_backend_names()
            self.status_logger.info(
                f"No backends configured, using all available: {enabled_names}"
            )

        for backend_name in enabled_names:
            try:
                # Get backend configuration
                backend_config = self.config_manager.get_backend_config(backend_name)

                # Build configuration parameters for backend creation
                config_params = {}
                if backend_config:
                    if backend_config.email:
                        config_params["email"] = backend_config.email

                    # Add cache_ttl_hours if specified in config dict
                    if "cache_ttl_hours" in backend_config.config:
                        config_params["cache_ttl_hours"] = backend_config.config[
                            "cache_ttl_hours"
                        ]

                # Create backend with configuration (uses factory or legacy)
                if config_params:
                    backend = backend_registry.create_backend(
                        backend_name, **config_params
                    )
                    self.detail_logger.debug(
                        f"Loaded backend: {backend_name} with configuration: {config_params}"
                    )
                else:
                    backend = backend_registry.get_backend(backend_name)
                    self.detail_logger.debug(
                        f"Loaded backend: {backend_name} (default configuration)"
                    )

                enabled_backends.append(backend)

            except ValueError as e:
                self.status_logger.warning(
                    f"Failed to load backend '{backend_name}': {e}"
                )

        return enabled_backends

    async def _query_backends(
        self, backends: list[Backend], query_input: QueryInput
    ) -> list[BackendResult]:
        """Query all backends concurrently with timeout and error handling."""
        tasks = []

        for backend in backends:
            backend_name = backend.get_name()
            self.detail_logger.info(
                f"Dispatcher: Starting query for backend: {backend_name}"
            )

            # Get backend-specific configuration
            backend_config = self.config_manager.get_backend_config(backend_name)
            timeout = backend_config.timeout if backend_config else 15

            # Create task with timeout and timing wrapper
            task = asyncio.create_task(
                self._query_backend_with_timing(backend, query_input, timeout),
                name=f"backend_{backend_name}",
            )
            tasks.append((backend_name, task))

        # Wait for all tasks to complete
        backend_results = []
        completed_tasks = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        # Process results and handle exceptions
        for i, result in enumerate(completed_tasks):
            backend_name = tasks[i][0]

            if isinstance(result, Exception):
                self.status_logger.error(
                    f"Backend {backend_name} failed with exception: {result}"
                )
                self.detail_logger.error(
                    f"Dispatcher: Backend {backend_name} failed: {result}"
                )
                # Create error result
                error_result = BackendResult(
                    backend_name=backend_name,
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=str(result),
                    response_time=0.0,
                    evidence_type="heuristic",  # Default for error cases
                )
                backend_results.append(error_result)
            elif isinstance(result, BackendResult):
                self.detail_logger.debug(
                    f"Backend {backend_name}: {result.status} (confidence: {result.confidence})"
                )
                self.detail_logger.info(
                    f"Dispatcher: Backend {backend_name} result: status={result.status}, assessment={result.assessment}, confidence={result.confidence}"
                )
                backend_results.append(result)
            else:
                # Handle unexpected result type
                self.status_logger.error(
                    f"Backend {backend_name} returned unexpected result type: {type(result)}"
                )
                error_result = BackendResult(
                    backend_name=backend_name,
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=f"Unexpected result type: {type(result)}",
                    response_time=0.0,
                    evidence_type="heuristic",  # Default for error cases
                )
                backend_results.append(error_result)

        return backend_results

    async def _query_backend_with_timing(
        self, backend: Backend, query_input: QueryInput, timeout: int
    ) -> BackendResult:
        """Query a backend and add execution timing information.

        Args:
            backend: The backend to query
            query_input: The query input
            timeout: Timeout in seconds

        Returns:
            BackendResult with execution_time_ms populated
        """
        result = await backend.query_with_timeout(query_input, timeout)

        # Convert response_time (seconds) to execution_time_ms (milliseconds)
        # response_time already contains the actual backend execution time
        result_dict = result.model_dump()
        result_dict["execution_time_ms"] = result.response_time * 1000
        result_dict["evidence_type"] = backend.get_evidence_type().value
        return BackendResult(**result_dict)

    def _calculate_assessment(
        self,
        query_input: QueryInput,
        backend_results: list[BackendResult],
        processing_time: float,
    ) -> AssessmentResult:
        """Calculate final assessment from backend results using simple heuristics.

        This orchestrates the assessment process by:
        1. Extracting retraction data
        2. Calculating weighted scores from backend results
        3. Making the final assessment decision
        4. Applying confidence adjustments
        """
        successful_results = [
            r for r in backend_results if r.status == BackendStatus.FOUND
        ]
        reasoning: list[str] = []

        # Extract retraction information
        retraction_info = self._extract_retraction_data(backend_results, reasoning)

        # Handle case with no successful results
        if not successful_results:
            return self._handle_no_results(
                query_input, backend_results, reasoning, processing_time
            )

        # Calculate weighted scores from backend results
        score_data = self._calculate_backend_scores(successful_results, reasoning)

        # Make final assessment decision
        return self._make_final_assessment(
            query_input,
            backend_results,
            successful_results,
            score_data,
            retraction_info,
            reasoning,
            processing_time,
        )

    def _extract_retraction_data(
        self, backend_results: list[BackendResult], reasoning: list[str]
    ) -> dict[str, Any]:
        """Extract and format retraction data from backend results.

        Returns:
            Dictionary with retraction information including risk_level,
            total_retractions, recent_retractions, and formatted messages.
        """
        retraction_result = next(
            (
                r
                for r in backend_results
                if r.backend_name == "retraction_watch"
                and r.status == BackendStatus.FOUND
            ),
            None,
        )

        if not retraction_result or not retraction_result.data:
            return {}

        retraction_data = retraction_result.data
        risk_level = retraction_data.get("risk_level")
        total_retractions = retraction_data.get("total_retractions", 0)
        recent_retractions = retraction_data.get("recent_retractions", 0)
        has_publication_data = retraction_data.get("has_publication_data", False)
        retraction_rate = retraction_data.get("retraction_rate")
        total_publications = retraction_data.get("total_publications")

        # Add retraction information to reasoning
        if risk_level in ["critical", "high"]:
            if has_publication_data and retraction_rate is not None:
                reasoning.append(
                    f"⚠️ {risk_level.upper()} retraction risk: "
                    f"{total_retractions} retractions ({recent_retractions} recent) "
                    f"= {retraction_rate:.3f}% rate ({total_publications:,} total publications)"
                )
            else:
                reasoning.append(
                    f"⚠️ {risk_level.upper()} retraction risk: "
                    f"{total_retractions} total retractions ({recent_retractions} recent)"
                )
        elif risk_level == "moderate":
            if has_publication_data and retraction_rate is not None:
                reasoning.append(
                    f"⚠️ Moderate retraction risk: "
                    f"{total_retractions} retractions ({recent_retractions} recent) "
                    f"= {retraction_rate:.3f}% rate ({total_publications:,} publications)"
                )
            else:
                reasoning.append(
                    f"⚠️ Moderate retraction risk: "
                    f"{total_retractions} total retractions ({recent_retractions} recent)"
                )
        elif total_retractions > 0:
            if has_publication_data and retraction_rate is not None:
                reasoning.append(
                    f"📊 {total_retractions} retraction(s): {retraction_rate:.3f}% rate "
                    f"(within normal range for {total_publications:,} publications)"
                )
            else:
                reasoning.append(
                    f"📊 {total_retractions} retraction(s) found in Retraction Watch database"
                )

        return {"risk_level": risk_level, "total_retractions": total_retractions}

    def _handle_no_results(
        self,
        query_input: QueryInput,
        backend_results: list[BackendResult],
        reasoning: list[str],
        processing_time: float,
    ) -> AssessmentResult:
        """Handle the case where no backends found the journal."""
        error_count = len(
            [r for r in backend_results if r.status == BackendStatus.ERROR]
        )
        not_found_count = len(
            [r for r in backend_results if r.status == BackendStatus.NOT_FOUND]
        )

        if error_count > 0:
            reasoning.append(f"{error_count} backend(s) encountered errors")
        if not_found_count > 0:
            reasoning.append(f"Not found in {not_found_count} backend(s)")

        return AssessmentResult(
            input_query=query_input.raw_input,
            assessment=AssessmentType.UNKNOWN,
            confidence=0.2 if not_found_count > 0 else 0.0,
            overall_score=0.0,
            backend_results=backend_results,
            metadata=None,
            reasoning=reasoning,
            processing_time=processing_time,
        )

    def _calculate_backend_scores(
        self, successful_results: list[BackendResult], reasoning: list[str]
    ) -> dict[str, Any]:
        """Calculate weighted scores from backend results.

        Returns:
            Dictionary containing predatory_weight, legitimate_weight,
            total_weight, predatory_count, and legitimate_count.
        """
        predatory_results = [
            r for r in successful_results if r.assessment == AssessmentType.PREDATORY
        ]
        legitimate_results = [
            r for r in successful_results if r.assessment == AssessmentType.LEGITIMATE
        ]

        total_predatory_weight = 0.0
        total_legitimate_weight = 0.0
        total_weight = 0.0

        for result in successful_results:
            # Skip retraction_watch in binary classification (it's a quality indicator)
            if result.backend_name == "retraction_watch":
                continue

            backend_config = self.config_manager.get_backend_config(result.backend_name)
            weight = backend_config.weight if backend_config else 1.0
            confidence_weighted = result.confidence * weight

            total_weight += weight

            if result.assessment == AssessmentType.PREDATORY:
                total_predatory_weight += confidence_weighted
                reasoning.append(
                    f"{result.backend_name}: predatory (confidence: {result.confidence:.2f})"
                )
            elif result.assessment == AssessmentType.LEGITIMATE:
                total_legitimate_weight += confidence_weighted
                reasoning.append(
                    f"{result.backend_name}: legitimate (confidence: {result.confidence:.2f})"
                )

        return {
            "predatory_weight": total_predatory_weight,
            "legitimate_weight": total_legitimate_weight,
            "total_weight": total_weight,
            "predatory_count": len(predatory_results),
            "legitimate_count": len(legitimate_results),
        }

    def _make_final_assessment(
        self,
        query_input: QueryInput,
        backend_results: list[BackendResult],
        successful_results: list[BackendResult],
        score_data: dict[str, Any],
        retraction_info: dict[str, Any],
        reasoning: list[str],
        processing_time: float,
    ) -> AssessmentResult:
        """Make the final assessment decision based on all available data."""
        total_predatory_weight = score_data["predatory_weight"]
        total_legitimate_weight = score_data["legitimate_weight"]
        total_weight = score_data["total_weight"]
        retraction_risk_level = retraction_info.get("risk_level")

        # Analyze evidence types to determine classification
        predatory_list_evidence = []
        legitimate_list_evidence = []
        heuristic_evidence = []

        for result in successful_results:
            if (
                result.evidence_type == EvidenceType.PREDATORY_LIST.value
                and result.assessment == AssessmentType.PREDATORY
            ):
                predatory_list_evidence.append(result)
            elif (
                result.evidence_type == EvidenceType.LEGITIMATE_LIST.value
                and result.assessment == AssessmentType.LEGITIMATE
            ):
                legitimate_list_evidence.append(result)
            elif result.evidence_type == EvidenceType.HEURISTIC.value:
                heuristic_evidence.append(result)

        # Decision logic based on issue #65 requirements
        if total_weight == 0:
            assessment = AssessmentType.UNKNOWN
            confidence = 0.1
            overall_score = 0.0
            reasoning.insert(0, "No assessment data available")

        elif len(predatory_list_evidence) > 0:
            # Rule: If ANY predatory list evidence exists, can be PREDATORY
            if total_predatory_weight > total_legitimate_weight:
                assessment = AssessmentType.PREDATORY
                confidence = min(0.95, total_predatory_weight / total_weight)
                overall_score = total_predatory_weight / total_weight
                reasoning.insert(
                    0,
                    f"Classified as predatory based on {len(predatory_list_evidence)} predatory list(s)",
                )

                # Cross-validate with retraction data
                if retraction_risk_level in ["critical", "high"]:
                    confidence = min(
                        CONFIDENCE_THRESHOLD_HIGH, confidence + AGREEMENT_BONUS_AMOUNT
                    )
                    reasoning.append(
                        "⚠️ High retraction rate corroborates predatory classification"
                    )
            else:
                # Predatory list evidence exists but legitimate evidence is stronger
                assessment = AssessmentType.LEGITIMATE
                confidence = min(0.9, total_legitimate_weight / total_weight)
                overall_score = total_legitimate_weight / total_weight
                reasoning.insert(
                    0,
                    "Classified as legitimate despite predatory list match - stronger legitimate evidence",
                )

        elif total_legitimate_weight > 0:
            # Only legitimate evidence (list or heuristic)
            assessment = AssessmentType.LEGITIMATE
            confidence = min(0.9, total_legitimate_weight / total_weight)
            overall_score = total_legitimate_weight / total_weight
            reasoning.insert(
                0,
                f"Classified as legitimate based on {score_data['legitimate_count']} source(s)",
            )

            # Flag if legitimate journal has concerning retraction patterns
            if retraction_risk_level in ["critical", "high"]:
                reasoning.append(
                    "⚠️ WARNING: High retraction rate despite legitimate classification"
                )
            elif retraction_risk_level == "moderate":
                reasoning.append(
                    "⚠️ NOTE: Moderate retraction rate - quality concerns exist"
                )

        elif total_predatory_weight > 0:
            # Rule: Predatory assessment based ONLY on heuristics = SUSPICIOUS
            assessment = AssessmentType.SUSPICIOUS
            confidence = min(
                0.85, total_predatory_weight / total_weight
            )  # Lower confidence for heuristic-only
            overall_score = total_predatory_weight / total_weight
            reasoning.insert(
                0,
                f"Classified as suspicious based on heuristic analysis only ({score_data['predatory_count']} source(s))",
            )

            # Retraction data supports suspicious classification
            if retraction_risk_level in ["critical", "high"]:
                confidence = min(0.95, confidence + AGREEMENT_BONUS_AMOUNT)
                reasoning.append(
                    "⚠️ High retraction rate supports suspicious classification"
                )

        else:
            assessment = AssessmentType.UNKNOWN
            confidence = 0.3
            overall_score = 0.0
            reasoning.insert(0, "Found in databases but assessment unclear")

            # Use retraction data as a warning flag when no clear classification
            if retraction_risk_level in ["critical", "high"]:
                reasoning.insert(
                    0, "⚠️ WARNING: High retraction rate detected - proceed with caution"
                )

        # Boost confidence if multiple backends agree (no disagreement)
        # Only apply bonus if all sources agree on the same assessment
        non_retraction_results = [
            r for r in successful_results if r.backend_name != "retraction_watch"
        ]

        if len(non_retraction_results) > 1:
            # Check if there's any disagreement
            predatory_sources = score_data["predatory_count"]
            legitimate_sources = score_data["legitimate_count"]

            # Only boost if sources agree (no contradiction)
            if predatory_sources > 0 and legitimate_sources == 0:
                # All sources agree it's predatory
                agreement_bonus = min(0.1, predatory_sources * 0.05)
                confidence = min(1.0, confidence + agreement_bonus)
                reasoning.append(
                    "Confidence boosted by agreement across multiple backends"
                )
            elif legitimate_sources > 0 and predatory_sources == 0:
                # All sources agree it's legitimate
                agreement_bonus = min(0.1, legitimate_sources * 0.05)
                confidence = min(1.0, confidence + agreement_bonus)
                reasoning.append(
                    "Confidence boosted by agreement across multiple backends"
                )
            elif predatory_sources > 0 and legitimate_sources > 0:
                # Sources disagree - note the disagreement
                reasoning.append(
                    f"⚠️ NOTE: Sources disagree ({predatory_sources} predatory, "
                    f"{legitimate_sources} legitimate) - review carefully"
                )

        return AssessmentResult(
            input_query=query_input.raw_input,
            assessment=assessment,
            confidence=confidence,
            overall_score=overall_score,
            backend_results=backend_results,
            metadata=None,
            reasoning=reasoning,
            processing_time=processing_time,
        )


# Global dispatcher instance
query_dispatcher = QueryDispatcher()
