# SPDX-License-Identifier: MIT
"""Query dispatcher for orchestrating backend assessment requests."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .backends.base import Backend, get_backend_registry
from .cache import AcronymCache
from .config import get_config_manager
from .constants import (
    AGREEMENT_BONUS_AMOUNT,
    CONFIDENCE_THRESHOLD_HIGH,
    CONFIDENCE_THRESHOLD_LOW,
)
from .cross_validation import get_cross_validation_registry
from .enums import AssessmentType, EvidenceType
from .fallback_chain import QueryFallbackChain
from .logging_config import get_detail_logger, get_status_logger
from .models import AssessmentResult, BackendResult, BackendStatus, QueryInput
from .normalizer import InputNormalizer, input_normalizer
from .quality_assessment import QualityAssessmentProcessor


@dataclass
class EvidenceClassification:
    """Classification of evidence by type from backend results."""

    predatory_list: list[BackendResult]
    legitimate_list: list[BackendResult]
    heuristic: list[BackendResult]


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
        """Initialize the QueryDispatcher.

        Loads configuration, initializes loggers, and sets up the central
        orchestration state.
        """
        self.config_manager = get_config_manager()
        self.config = self.config_manager.load_config()
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()
        self.cross_validation_registry = get_cross_validation_registry()
        self.quality_processor = QualityAssessmentProcessor()

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
                acronym_expanded_from=query_input.acronym_expanded_from,
                acronym_expansion_used=bool(query_input.acronym_expanded_from),
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

        # Acronym fallback: If initial query yields no confident results and input looks
        # like an acronym with a cached expansion, retry with the expanded name
        return await self._try_acronym_fallback(
            assessment_result, query_input, enabled_backends, start_time
        )

    def _apply_cross_validation(
        self, backend_results: list[BackendResult], reasoning: list[str]
    ) -> list[BackendResult]:
        """Apply cross-validation to backend results and adjust confidence scores.

        Args:
            backend_results: List of backend results to cross-validate
            reasoning: List to append reasoning messages to

        Returns:
            List of backend results with confidence adjustments applied
        """
        successful_results = [
            r for r in backend_results if r.status == BackendStatus.FOUND
        ]

        if len(successful_results) < 2:
            self.detail_logger.debug("Insufficient results for cross-validation")
            return backend_results

        # Create result lookup by backend name for efficient access
        # Include ALL results (not just successful) for cross-validation
        result_map = {r.backend_name: r for r in backend_results}

        # Get all registered pairs from the cross-validation registry
        registered_pairs = self.cross_validation_registry.get_registered_pairs()

        cross_validation_applied = False
        adjusted_results = []

        for result in backend_results:
            if result.status != BackendStatus.FOUND:
                # Keep non-successful results unchanged
                adjusted_results.append(result)
                continue

            # Check if this result can be cross-validated with any other result
            confidence_adjustment = 0.0
            cross_validation_data = None
            backend_name = result.backend_name

            for backend1, backend2 in registered_pairs:
                if backend_name == backend1 and backend2 in result_map:
                    other_result = result_map[backend2]
                elif backend_name == backend2 and backend1 in result_map:
                    other_result = result_map[backend1]
                else:
                    continue

                # Apply cross-validation for this pair
                validation_result = self.cross_validation_registry.validate_pair(
                    backend_name, result, other_result.backend_name, other_result
                )

                if validation_result:
                    confidence_adjustment = validation_result.get(
                        "confidence_adjustment", 0.0
                    )
                    cross_validation_data = validation_result
                    cross_validation_applied = True

                    self.detail_logger.debug(
                        f"Cross-validation applied between {backend_name} and {other_result.backend_name}: "
                        f"adjustment={confidence_adjustment:+.3f}"
                    )

                    # Add cross-validation reasoning
                    if validation_result.get("reasoning"):
                        reasoning.extend(
                            [
                                f"Cross-validation ({backend_name} ↔ {other_result.backend_name}):"
                            ]
                            + [
                                f"  {reason}"
                                for reason in validation_result["reasoning"][:3]
                            ]
                        )

                    break  # Apply only first matching cross-validation

            # Create adjusted result
            new_confidence = max(
                0.0, min(1.0, result.confidence + confidence_adjustment)
            )

            # Create new result with adjusted confidence and cross-validation data
            adjusted_result = BackendResult(
                backend_name=result.backend_name,
                status=result.status,
                confidence=new_confidence,
                assessment=result.assessment,
                data={
                    **result.data,
                    **(
                        {"cross_validation": cross_validation_data}
                        if cross_validation_data
                        else {}
                    ),
                },
                sources=result.sources,
                error_message=result.error_message,
                response_time=result.response_time,
                cached=result.cached,
                execution_time_ms=result.execution_time_ms,
                evidence_type=result.evidence_type,
                fallback_chain=result.fallback_chain,
            )
            adjusted_results.append(adjusted_result)

        if cross_validation_applied:
            self.detail_logger.info(
                "Cross-validation adjustments applied to backend results"
            )

        return adjusted_results

    async def _try_acronym_fallback(
        self,
        assessment_result: AssessmentResult,
        query_input: QueryInput,
        enabled_backends: list[Backend],
        start_time: float,
    ) -> AssessmentResult:
        """Try acronym/variant expansion fallback if initial results are not confident.

        Two lookup paths are attempted in order:
        1. Standalone acronym (e.g. "ICML") → direct ``get_full_name_for_acronym`` lookup.
        2. Abbreviated variant form (e.g. "ieee trans. pattern anal. mach. intell.")
           → ``get_canonical_for_variant`` search within the variants JSON array.

        Args:
            assessment_result: The initial assessment result
            query_input: The original query input
            enabled_backends: List of enabled backends for re-querying
            start_time: Start time for processing time calculation

        Returns:
            Either the original assessment_result or improved result from expansion
        """
        if self._should_try_acronym_fallback(assessment_result, query_input):
            normalizer = InputNormalizer()
            acronym_cache = AcronymCache()

            # Use original venue type for all acronym/variant lookups
            entity_type = query_input.venue_type.value
            expanded_name: str | None = None

            # Path 1: standalone acronym (e.g. "ICML") → direct acronym lookup
            if normalizer._is_standalone_acronym(query_input.raw_input):
                expanded_name = acronym_cache.get_full_name_for_acronym(
                    query_input.raw_input, entity_type
                )

            # Path 2: abbreviated form (e.g. "ieee trans. pattern anal. mach. intell.")
            # → search within the variants JSON array
            if not expanded_name:
                expanded_name = acronym_cache.get_canonical_for_variant(
                    query_input.raw_input, entity_type
                )

            if expanded_name:
                self.status_logger.info(
                    f"No confident results for '{query_input.raw_input}'. "
                    f"Retrying with expanded name: '{expanded_name}'"
                )

                # Create new query input with expanded name
                # Create acronym lookup closure that uses the same entity_type
                def acronym_lookup_for_type(acr: str) -> str | None:
                    return acronym_cache.get_full_name_for_acronym(acr, entity_type)

                expanded_query = input_normalizer.normalize(
                    expanded_name,
                    acronym_lookup=acronym_lookup_for_type,
                )

                # Store any new acronym mappings discovered during expansion
                for (
                    acronym,
                    full_name,
                ) in expanded_query.extracted_acronym_mappings.items():
                    acronym_cache.store_acronym_mapping(
                        acronym,
                        full_name,
                        entity_type,
                        source="dispatcher_expansion",
                    )

                # Re-query backends with expanded name
                retry_results = await self._query_backends(
                    enabled_backends, expanded_query
                )

                # Calculate new assessment
                retry_assessment = self._calculate_assessment(
                    expanded_query, retry_results, time.time() - start_time
                )

                # If retry gave better results, use it and mark acronym expansion
                if retry_assessment.confidence > assessment_result.confidence:
                    retry_assessment.acronym_expanded_from = query_input.raw_input
                    retry_assessment.acronym_expansion_used = True
                    return retry_assessment

        return assessment_result

    def _get_enabled_backends(self) -> list[Backend]:
        """Get list of enabled and configured backends."""
        # Auto-register custom lists before getting backends
        from .cache.custom_list_manager import auto_register_custom_lists

        auto_register_custom_lists()

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

                # Create backend with configuration (custom config vs defaults)
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
                    fallback_chain=QueryFallbackChain([]),
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
                    fallback_chain=QueryFallbackChain([]),
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

    def _should_try_acronym_fallback(
        self, assessment_result: AssessmentResult, query_input: QueryInput
    ) -> bool:
        """Determine if we should try acronym expansion fallback.

        Acronym fallback is attempted when:
        - Initial assessment is UNKNOWN or has low confidence
        - No backends returned FOUND status
        - Input hasn't already been expanded from an acronym

        Args:
            assessment_result: The initial assessment result
            query_input: The original query input

        Returns:
            True if acronym fallback should be attempted
        """
        # Don't retry if we already used acronym expansion
        if query_input.acronym_expanded_from:
            return False

        # Retry if assessment is UNKNOWN
        if assessment_result.assessment == AssessmentType.UNKNOWN:
            return True

        # Retry if confidence is very low
        if assessment_result.confidence < CONFIDENCE_THRESHOLD_LOW:
            return True

        # Retry if no backends found anything
        found_count = sum(
            1
            for r in assessment_result.backend_results
            if r.status == BackendStatus.FOUND
        )
        if found_count == 0:
            return True

        return False

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

        # Extract quality assessment information
        quality_info = self.quality_processor.extract_quality_data(
            backend_results, reasoning
        )

        # Handle case with no successful results
        if not successful_results:
            return self._handle_no_results(
                query_input, backend_results, reasoning, processing_time
            )

        # Apply cross-validation adjustments to backend results
        backend_results = self._apply_cross_validation(backend_results, reasoning)

        # Refresh successful results after cross-validation adjustments
        successful_results = [
            r for r in backend_results if r.status == BackendStatus.FOUND
        ]

        # Calculate weighted scores from backend results
        score_data = self._calculate_backend_scores(successful_results, reasoning)

        # Make final assessment decision
        return self._make_final_assessment(
            query_input,
            backend_results,
            successful_results,
            score_data,
            quality_info,
            reasoning,
            processing_time,
        )

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
            acronym_expanded_from=query_input.acronym_expanded_from,
            acronym_expansion_used=bool(query_input.acronym_expanded_from),
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
            # Skip quality indicators in binary classification
            if result.evidence_type == EvidenceType.QUALITY_INDICATOR.value:
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

    def _classify_evidence_by_type(
        self, successful_results: list[BackendResult]
    ) -> EvidenceClassification:
        """Extract and categorize evidence types from backend results.

        Args:
            successful_results: List of successful backend results

        Returns:
            EvidenceClassification containing categorized evidence
        """
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

        return EvidenceClassification(
            predatory_list=predatory_list_evidence,
            legitimate_list=legitimate_list_evidence,
            heuristic=heuristic_evidence,
        )

    def _assess_from_predatory_evidence(
        self,
        evidence: EvidenceClassification,
        total_predatory_weight: float,
        total_legitimate_weight: float,
        total_weight: float,
        quality_risk_level: str | None,
        reasoning: list[str],
    ) -> tuple[str, float, float]:
        """Determine assessment when predatory list evidence exists.

        Compares predatory vs legitimate weights to make final determination.

        Returns:
            Tuple of (assessment, confidence, overall_score)
        """
        # Compare weights to determine if predatory or legitimate
        if total_predatory_weight > total_legitimate_weight:
            assessment = AssessmentType.PREDATORY
            confidence = min(0.95, total_predatory_weight / total_weight)
            overall_score = total_predatory_weight / total_weight
            reasoning.insert(
                0,
                f"Classified as predatory based on {len(evidence.predatory_list)} predatory list(s)",
            )

            # Cross-validate with quality assessment data
            if quality_risk_level in ["critical", "high"]:
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

        return (assessment, confidence, overall_score)

    def _assess_from_legitimate_evidence(
        self,
        total_legitimate_weight: float,
        total_weight: float,
        legitimate_count: int,
        quality_risk_level: str | None,
        reasoning: list[str],
    ) -> tuple[str, float, float]:
        """Determine assessment when only legitimate evidence exists.

        Args:
            total_legitimate_weight: Weighted legitimate score
            total_weight: Total weight from all backends
            legitimate_count: Number of legitimate sources
            quality_risk_level: Risk level from quality assessment data
            reasoning: List to append reasoning messages to

        Returns:
            Tuple of (assessment, confidence, overall_score)
        """
        assessment = AssessmentType.LEGITIMATE
        confidence = min(0.9, total_legitimate_weight / total_weight)
        overall_score = total_legitimate_weight / total_weight
        reasoning.insert(
            0,
            f"Classified as legitimate based on {legitimate_count} source(s)",
        )

        # Flag if legitimate journal has concerning quality patterns
        if quality_risk_level in ["critical", "high"]:
            reasoning.append(
                "⚠️ WARNING: High retraction rate despite legitimate classification"
            )
        elif quality_risk_level == "moderate":
            reasoning.append(
                "⚠️ NOTE: Moderate retraction rate - quality concerns exist"
            )

        return (assessment, confidence, overall_score)

    def _assess_from_heuristic_evidence(
        self,
        total_predatory_weight: float,
        total_weight: float,
        predatory_count: int,
        quality_risk_level: str | None,
        reasoning: list[str],
    ) -> tuple[str, float, float]:
        """Determine assessment when only heuristic evidence exists.

        Args:
            total_predatory_weight: Weighted predatory score
            total_weight: Total weight from all backends
            predatory_count: Number of predatory sources
            quality_risk_level: Risk level from quality assessment data
            reasoning: List to append reasoning messages to

        Returns:
            Tuple of (assessment, confidence, overall_score)
        """
        assessment = AssessmentType.SUSPICIOUS
        confidence = min(
            0.85, total_predatory_weight / total_weight
        )  # Lower confidence for heuristic-only
        overall_score = total_predatory_weight / total_weight
        reasoning.insert(
            0,
            f"Classified as suspicious based on heuristic analysis only ({predatory_count} source(s))",
        )

        # Quality assessment data supports suspicious classification
        if quality_risk_level in ["critical", "high"]:
            confidence = min(0.95, confidence + AGREEMENT_BONUS_AMOUNT)
            reasoning.append(
                "⚠️ High retraction rate supports suspicious classification"
            )

        return (assessment, confidence, overall_score)

    def _apply_agreement_bonus(
        self,
        assessment: str,
        confidence: float,
        successful_results: list[BackendResult],
        score_data: dict[str, Any],
        reasoning: list[str],
    ) -> float:
        """Apply confidence bonus when multiple backends agree.

        Only applies bonus if all sources agree on the same assessment (no disagreement).

        Returns:
            Updated confidence score
        """
        # Exclude retraction_watch from agreement calculation
        non_retraction_results = [
            r for r in successful_results if r.backend_name != "retraction_watch"
        ]

        if len(non_retraction_results) <= 1:
            return confidence

        predatory_sources = score_data["predatory_count"]
        legitimate_sources = score_data["legitimate_count"]

        # Only boost if sources agree (no contradiction)
        if predatory_sources > 0 and legitimate_sources == 0:
            # All sources agree it's predatory
            agreement_bonus = min(0.1, predatory_sources * 0.05)
            confidence = min(1.0, confidence + agreement_bonus)
            reasoning.append("Confidence boosted by agreement across multiple backends")
        elif legitimate_sources > 0 and predatory_sources == 0:
            # All sources agree it's legitimate
            agreement_bonus = min(0.1, legitimate_sources * 0.05)
            confidence = min(1.0, confidence + agreement_bonus)
            reasoning.append("Confidence boosted by agreement across multiple backends")
        elif predatory_sources > 0 and legitimate_sources > 0:
            # Sources disagree - note the disagreement
            reasoning.append(
                f"⚠️ NOTE: Sources disagree ({predatory_sources} predatory, "
                f"{legitimate_sources} legitimate) - review carefully"
            )

        return confidence

    def _determine_assessment_from_evidence(
        self,
        evidence: EvidenceClassification,
        score_data: dict[str, Any],
        quality_risk_level: str | None,
        reasoning: list[str],
    ) -> tuple[str, float, float]:
        """Determine assessment classification from evidence.

        Decision logic based on issue #65 requirements:
        - Predatory list evidence takes precedence
        - Legitimate evidence is second priority
        - Heuristic-only evidence results in SUSPICIOUS
        - No evidence results in UNKNOWN

        Args:
            evidence: Classified evidence by type
            score_data: Dictionary with weights and counts
            quality_risk_level: Risk level from quality assessment data
            reasoning: List to append reasoning messages to

        Returns:
            Tuple of (assessment, confidence, overall_score)
        """
        total_predatory_weight = score_data["predatory_weight"]
        total_legitimate_weight = score_data["legitimate_weight"]
        total_weight = score_data["total_weight"]

        if total_weight == 0:
            reasoning.insert(0, "No assessment data available")
            return (AssessmentType.UNKNOWN, 0.1, 0.0)

        if len(evidence.predatory_list) > 0:
            # Rule: If ANY predatory list evidence exists, can be PREDATORY
            return self._assess_from_predatory_evidence(
                evidence,
                total_predatory_weight,
                total_legitimate_weight,
                total_weight,
                quality_risk_level,
                reasoning,
            )

        if total_legitimate_weight > 0:
            # Only legitimate evidence (list or heuristic)
            return self._assess_from_legitimate_evidence(
                total_legitimate_weight,
                total_weight,
                score_data["legitimate_count"],
                quality_risk_level,
                reasoning,
            )

        if total_predatory_weight > 0:
            # Rule: Predatory assessment based ONLY on heuristics = SUSPICIOUS
            return self._assess_from_heuristic_evidence(
                total_predatory_weight,
                total_weight,
                score_data["predatory_count"],
                quality_risk_level,
                reasoning,
            )

        # Unknown case - use quality data as warning flag
        reasoning.insert(0, "Found in databases but assessment unclear")
        if quality_risk_level in ["critical", "high"]:
            reasoning.insert(
                0, "⚠️ WARNING: High retraction rate detected - proceed with caution"
            )
        return (AssessmentType.UNKNOWN, CONFIDENCE_THRESHOLD_LOW, 0.0)

    def _make_final_assessment(
        self,
        query_input: QueryInput,
        backend_results: list[BackendResult],
        successful_results: list[BackendResult],
        score_data: dict[str, Any],
        quality_info: dict[str, Any],
        reasoning: list[str],
        processing_time: float,
    ) -> AssessmentResult:
        """Make the final assessment decision based on all available data.

        This method orchestrates the final assessment by:
        1. Classifying evidence by type
        2. Determining base assessment from evidence
        3. Applying agreement bonuses
        4. Building final result
        """
        # Classify evidence by type
        evidence = self._classify_evidence_by_type(successful_results)

        # Determine base assessment from evidence
        assessment, confidence, overall_score = (
            self._determine_assessment_from_evidence(
                evidence, score_data, quality_info.get("risk_level"), reasoning
            )
        )

        # Apply agreement bonuses
        confidence = self._apply_agreement_bonus(
            assessment, confidence, successful_results, score_data, reasoning
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
            acronym_expanded_from=query_input.acronym_expanded_from,
            acronym_expansion_used=bool(query_input.acronym_expanded_from),
        )


# Global dispatcher instance
query_dispatcher = QueryDispatcher()
