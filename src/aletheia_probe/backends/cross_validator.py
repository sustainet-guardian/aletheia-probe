# SPDX-License-Identifier: MIT
"""Cross-validation backend that combines OpenAlex and Crossref analysis."""

import asyncio
import time
from typing import Any

from ..constants import CONFIDENCE_THRESHOLD_LOW
from ..enums import AssessmentType
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus, QueryInput
from ..validation import validate_email
from .base import ApiBackendWithCache, get_backend_registry
from .crossref_analyzer import CrossrefAnalyzerBackend
from .openalex_analyzer import OpenAlexAnalyzerBackend


class CrossValidatorBackend(ApiBackendWithCache):
    """Backend that combines and cross-validates OpenAlex and Crossref data."""

    def __init__(
        self, email: str = "noreply@aletheia-probe.org", cache_ttl_hours: int = 24
    ):
        """Initialize cross-validation backend.

        Args:
            email: Email for API access
            cache_ttl_hours: Cache TTL in hours

        Raises:
            TypeError: If email is not a string
            ValueError: If email format is invalid
        """
        super().__init__(cache_ttl_hours)
        self.email = validate_email(email)
        self.openalex_backend = OpenAlexAnalyzerBackend(email, cache_ttl_hours)
        self.crossref_backend = CrossrefAnalyzerBackend(email, cache_ttl_hours)
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    def get_name(self) -> str:
        """Return backend name."""
        return "cross_validator"

    async def _query_api(self, query_input: QueryInput) -> BackendResult:
        """Query both backends and cross-validate results."""
        start_time = time.time()
        self.detail_logger.debug(f"Starting cross-validation for: {query_input}")

        try:
            # Query both backends concurrently
            self.detail_logger.debug("Querying OpenAlex and Crossref concurrently")
            openalex_result, crossref_result = await asyncio.gather(
                self.openalex_backend.query(query_input),
                self.crossref_backend.query(query_input),
                return_exceptions=True,
            )

            response_time = time.time() - start_time

            # Handle exceptions
            if isinstance(openalex_result, Exception):
                self.detail_logger.error(f"OpenAlex query failed: {openalex_result}")
                openalex_result = BackendResult(
                    backend_name=self.openalex_backend.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=str(openalex_result),
                    response_time=0.0,
                    cached=False,  # Errors are not cached
                )

            if isinstance(crossref_result, Exception):
                self.detail_logger.error(f"Crossref query failed: {crossref_result}")
                crossref_result = BackendResult(
                    backend_name=self.crossref_backend.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=str(crossref_result),
                    response_time=0.0,
                    cached=False,  # Errors are not cached
                )

            # Perform cross-validation analysis (check for errors first)
            if isinstance(openalex_result, BaseException) or isinstance(
                crossref_result, BaseException
            ):
                self.status_logger.error("Critical error during backend querying")
                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=AssessmentType.INSUFFICIENT_DATA,
                    data={},
                    sources=[],
                    error_message="Backend error during cross-validation",
                    response_time=response_time,
                    cached=False,  # Errors are not cached
                )

            self.detail_logger.debug(
                "Both backends queried successfully, starting analysis"
            )
            validation_result = self._cross_validate_results(
                openalex_result, crossref_result, query_input
            )

            self.detail_logger.debug(
                f"Cross-validation complete. Status: {validation_result['status']}, "
                f"Assessment: {validation_result['assessment']}"
            )

            return BackendResult(
                backend_name=self.get_name(),
                status=validation_result["status"],
                confidence=validation_result["confidence"],
                assessment=validation_result["assessment"],
                data={
                    "openalex_result": (
                        openalex_result.model_dump()
                        if hasattr(openalex_result, "model_dump")
                        else openalex_result.__dict__
                    ),
                    "crossref_result": (
                        crossref_result.model_dump()
                        if hasattr(crossref_result, "model_dump")
                        else crossref_result.__dict__
                    ),
                    "cross_validation": validation_result,
                    "consistency_checks": validation_result["consistency_checks"],
                    "combined_flags": validation_result["combined_flags"],
                },
                sources=list(set(openalex_result.sources + crossref_result.sources)),
                error_message=None,
                response_time=response_time,
                cached=False,  # Will be set by ApiBackendWithCache.query() when result is cached
            )

        except Exception as e:
            response_time = time.time() - start_time
            self.status_logger.error(f"Cross-validation failed: {e}")
            self.detail_logger.exception("Detailed error in cross-validation:")
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
                cached=False,  # Errors are not cached
            )

    def _extract_backend_data(
        self, openalex_result: BackendResult, crossref_result: BackendResult
    ) -> tuple[bool, bool, dict[str, Any], dict[str, Any]]:
        """Extract and prepare data from both backend results."""
        openalex_found = openalex_result.status == BackendStatus.FOUND
        crossref_found = crossref_result.status == BackendStatus.FOUND

        openalex_data = (
            openalex_result.data.get("openalex_data", {}) if openalex_found else {}
        )
        crossref_data = (
            crossref_result.data.get("crossref_data", {}) if crossref_found else {}
        )

        return openalex_found, crossref_found, openalex_data, crossref_data

    def _collect_combined_flags(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        openalex_found: bool,
        crossref_found: bool,
    ) -> dict[str, list[str]]:
        """Collect red and green flags from both backends."""
        combined_flags: dict[str, list[str]] = {
            "red_flags": [],
            "green_flags": [],
        }

        if openalex_found:
            openalex_analysis = openalex_result.data.get("analysis", {})
            combined_flags["red_flags"].extend(
                [f"OpenAlex: {flag}" for flag in openalex_analysis.get("red_flags", [])]
            )
            combined_flags["green_flags"].extend(
                [
                    f"OpenAlex: {flag}"
                    for flag in openalex_analysis.get("green_flags", [])
                ]
            )

        if crossref_found:
            crossref_analysis = crossref_result.data.get("analysis", {})
            combined_flags["red_flags"].extend(
                [f"Crossref: {flag}" for flag in crossref_analysis.get("red_flags", [])]
            )
            combined_flags["green_flags"].extend(
                [
                    f"Crossref: {flag}"
                    for flag in crossref_analysis.get("green_flags", [])
                ]
            )

        return combined_flags

    def _handle_no_data_found(
        self, combined_flags: dict[str, list[str]]
    ) -> dict[str, Any]:
        """Handle case where neither backend found data."""
        return {
            "status": BackendStatus.NOT_FOUND,
            "assessment": None,
            "confidence": 0.0,
            "consistency_checks": [],
            "combined_flags": combined_flags,
            "reasoning": ["Journal not found in either OpenAlex or Crossref databases"],
        }

    def _handle_single_backend_result(
        self,
        result: BackendResult,
        backend_name: str,
        other_backend_name: str,
        combined_flags: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Handle case where only one backend found data."""
        return {
            "status": BackendStatus.FOUND,
            "assessment": result.assessment,
            "confidence": max(0.1, result.confidence * 0.8),
            "consistency_checks": [
                f"Only found in {backend_name}, not in {other_backend_name}"
            ],
            "combined_flags": combined_flags,
            "reasoning": [
                f"Assessment based solely on {backend_name} data",
                "Confidence reduced due to lack of cross-validation",
            ]
            + result.data.get("analysis", {}).get("reasoning", []),
        }

    def _cross_validate_results(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        query_input: QueryInput,
    ) -> dict[str, Any]:
        """Cross-validate results from both backends."""
        # Extract data and determine what was found
        openalex_found, crossref_found, openalex_data, crossref_data = (
            self._extract_backend_data(openalex_result, crossref_result)
        )

        self.detail_logger.debug(
            f"Data found - OpenAlex: {openalex_found}, Crossref: {crossref_found}"
        )

        # Collect flags from both backends
        combined_flags = self._collect_combined_flags(
            openalex_result, crossref_result, openalex_found, crossref_found
        )

        # Perform consistency checks if both backends found data
        consistency_checks = []
        if openalex_found and crossref_found:
            consistency_checks = self._perform_consistency_checks(
                openalex_data, crossref_data, query_input
            )

        # Handle different scenarios
        if not openalex_found and not crossref_found:
            return self._handle_no_data_found(combined_flags)

        if openalex_found and not crossref_found:
            return self._handle_single_backend_result(
                openalex_result, "OpenAlex", "Crossref", combined_flags
            )

        if crossref_found and not openalex_found:
            return self._handle_single_backend_result(
                crossref_result, "Crossref", "OpenAlex", combined_flags
            )

        # Both backends found data - perform full cross-validation
        return self._combine_assessments(
            openalex_result, crossref_result, consistency_checks, combined_flags
        )

    def _perform_consistency_checks(
        self,
        openalex_data: dict[str, Any],
        crossref_data: dict[str, Any],
        query_input: QueryInput,
    ) -> list[str]:
        """Perform consistency checks between OpenAlex and Crossref data."""
        self.detail_logger.debug("Performing consistency checks between backends")
        checks = []

        # Check publisher name consistency
        openalex_publisher = openalex_data.get("publisher", "").strip().lower()
        crossref_publisher = crossref_data.get("publisher", "").strip().lower()

        if openalex_publisher and crossref_publisher:
            # Simple similarity check (contains one in the other)
            if (
                openalex_publisher in crossref_publisher
                or crossref_publisher in openalex_publisher
            ):
                checks.append(
                    f"✓ Publisher names consistent: '{openalex_data.get('publisher')}' (OpenAlex) matches '{crossref_data.get('publisher')}' (Crossref)"
                )
            else:
                checks.append(
                    f"⚠️ Publisher name mismatch: '{openalex_data.get('publisher')}' (OpenAlex) vs '{crossref_data.get('publisher')}' (Crossref)"
                )

        # Check DOAJ listing consistency
        openalex_in_doaj = openalex_data.get("is_in_doaj", False)
        # Crossref doesn't directly track DOAJ, but we can infer from license practices
        crossref_metrics = crossref_data.get("coverage", {})
        crossref_license_score = crossref_metrics.get("licenses", 0)

        if openalex_in_doaj:
            if crossref_license_score >= 50:
                checks.append(
                    "✓ DOAJ listing consistent: Listed in DOAJ and good license reporting in Crossref"
                )
            else:
                checks.append(
                    "⚠️ DOAJ inconsistency: Listed in DOAJ but poor license reporting in Crossref"
                )

        # Check publication volume correlation
        openalex_total = openalex_data.get("total_publications", 0)
        crossref_total = crossref_data.get("counts", {}).get("total-dois", 0)

        if openalex_total > 0 and crossref_total > 0:
            ratio = min(openalex_total, crossref_total) / max(
                openalex_total, crossref_total
            )
            if ratio >= 0.7:  # Within 30% of each other
                checks.append(
                    f"✓ Publication volumes consistent: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (Crossref)"
                )
            elif ratio >= 0.3:
                checks.append(
                    f"⚠️ Moderate publication volume difference: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (Crossref)"
                )
            else:
                checks.append(
                    f"⚠️ Large publication volume discrepancy: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (Crossref)"
                )

        # Check activity timeline consistency
        openalex_last_year = openalex_data.get("last_publication_year")
        crossref_current_dois = crossref_data.get("counts", {}).get("current-dois", 0)

        if openalex_last_year and crossref_current_dois:
            current_year = 2024  # Could use datetime.now().year
            if openalex_last_year >= current_year - 2 and crossref_current_dois > 0:
                checks.append("✓ Recent activity consistent in both databases")
            elif openalex_last_year < current_year - 3 and crossref_current_dois == 0:
                checks.append("✓ Inactive status consistent in both databases")
            else:
                checks.append("⚠️ Activity status inconsistent between databases")

        # Log warnings found
        warnings = [c for c in checks if "⚠️" in c]
        if warnings:
            self.detail_logger.debug(f"Consistency warnings found: {warnings}")
        else:
            self.detail_logger.debug("No consistency warnings found")

        return checks

    def _determine_final_assessment(
        self,
        openalex_assessment: Any,
        crossref_assessment: Any,
        openalex_confidence: float,
        crossref_confidence: float,
    ) -> tuple[Any, float, float, bool]:
        """Determine final assessment based on agreement/disagreement between backends."""
        agreement_bonus = 0.0
        assessment_agreement = False

        if (
            openalex_assessment == crossref_assessment
            and openalex_assessment is not None
        ):
            # Both backends agree on the assessment
            agreement_bonus = 0.15
            assessment_agreement = True
            final_assessment = openalex_assessment
            base_confidence = max(openalex_confidence, crossref_confidence)
        elif openalex_assessment is None and crossref_assessment is not None:
            # Only Crossref has an assessment
            final_assessment = crossref_assessment
            base_confidence = crossref_confidence * 0.9
        elif crossref_assessment is None and openalex_assessment is not None:
            # Only OpenAlex has an assessment
            final_assessment = openalex_assessment
            base_confidence = openalex_confidence * 0.9
        elif openalex_assessment != crossref_assessment:
            # Disagreement between backends
            if openalex_confidence > crossref_confidence * 1.2:
                final_assessment = (
                    openalex_assessment or AssessmentType.INSUFFICIENT_DATA
                )
                base_confidence = openalex_confidence * 0.7
            elif crossref_confidence > openalex_confidence * 1.2:
                final_assessment = (
                    crossref_assessment or AssessmentType.INSUFFICIENT_DATA
                )
                base_confidence = crossref_confidence * 0.7
            else:
                # Confidence levels are similar but assessments disagree - inconclusive
                final_assessment = None
                base_confidence = CONFIDENCE_THRESHOLD_LOW
        else:
            # Both backends returned None assessment
            final_assessment = None
            base_confidence = 0.2

        return final_assessment, base_confidence, agreement_bonus, assessment_agreement

    def _apply_confidence_adjustments(
        self,
        base_confidence: float,
        agreement_bonus: float,
        consistency_checks: list[str],
    ) -> float:
        """Apply agreement bonuses and consistency check adjustments to confidence."""
        final_confidence = min(1.0, base_confidence + agreement_bonus)

        # Consistency check adjustments
        warning_count = sum(1 for check in consistency_checks if "⚠️" in check)
        success_count = sum(1 for check in consistency_checks if "✓" in check)

        if warning_count >= 2:
            final_confidence = max(0.1, final_confidence - 0.1)
        elif success_count >= 2:
            final_confidence = min(1.0, final_confidence + 0.05)

        return final_confidence

    def _generate_reasoning(
        self,
        assessment_agreement: bool,
        final_assessment: Any,
        agreement_bonus: float,
        openalex_assessment: Any,
        crossref_assessment: Any,
        consistency_checks: list[str],
        openalex_result: BackendResult,
        crossref_result: BackendResult,
    ) -> list[str]:
        """Generate reasoning based on assessment results."""
        reasoning = []

        if assessment_agreement:
            reasoning.append(
                f"Both OpenAlex and Crossref analysis agree: {final_assessment}"
            )
            reasoning.append(
                f"Cross-validation confidence bonus: +{agreement_bonus:.0%}"
            )
        elif openalex_assessment != crossref_assessment:
            reasoning.append(
                f"Backend disagreement: OpenAlex='{openalex_assessment}', Crossref='{crossref_assessment}'"
            )
            if final_assessment:
                reasoning.append(
                    f"Defaulting to higher confidence assessment: {final_assessment}"
                )

        if consistency_checks:
            reasoning.append("Consistency checks:")
            reasoning.extend([f"  {check}" for check in consistency_checks])

        # Add summaries from individual backends
        if openalex_result.data.get("analysis", {}).get("reasoning"):
            reasoning.append("OpenAlex reasoning:")
            reasoning.extend(
                [f"  {r}" for r in openalex_result.data["analysis"]["reasoning"][:3]]
            )

        if crossref_result.data.get("analysis", {}).get("reasoning"):
            reasoning.append("Crossref reasoning:")
            reasoning.extend(
                [f"  {r}" for r in crossref_result.data["analysis"]["reasoning"][:3]]
            )

        return reasoning

    def _combine_assessments(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        consistency_checks: list[str],
        combined_flags: dict[str, Any],
    ) -> dict[str, Any]:
        """Combine assessments from both backends with cross-validation."""
        openalex_assessment = openalex_result.assessment
        crossref_assessment = crossref_result.assessment
        openalex_confidence = openalex_result.confidence
        crossref_confidence = crossref_result.confidence

        # Determine final assessment and base confidence
        final_assessment, base_confidence, agreement_bonus, assessment_agreement = (
            self._determine_final_assessment(
                openalex_assessment,
                crossref_assessment,
                openalex_confidence,
                crossref_confidence,
            )
        )

        # Apply confidence adjustments
        final_confidence = self._apply_confidence_adjustments(
            base_confidence, agreement_bonus, consistency_checks
        )

        self.detail_logger.debug(
            f"Assessment agreement: {assessment_agreement}, Bonus: {agreement_bonus}, "
            f"Final Confidence: {final_confidence}"
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            assessment_agreement,
            final_assessment,
            agreement_bonus,
            openalex_assessment,
            crossref_assessment,
            consistency_checks,
            openalex_result,
            crossref_result,
        )

        return {
            "status": BackendStatus.FOUND,
            "assessment": final_assessment,
            "confidence": final_confidence,
            "consistency_checks": consistency_checks,
            "combined_flags": combined_flags,
            "reasoning": reasoning,
            "agreement": assessment_agreement,
            "individual_results": {
                "openalex": {
                    "assessment": openalex_assessment,
                    "confidence": openalex_confidence,
                },
                "crossref": {
                    "assessment": crossref_assessment,
                    "confidence": crossref_confidence,
                },
            },
        }


# Register the backend with factory for configuration support
get_backend_registry().register_factory(
    "cross_validator",
    lambda email="noreply@aletheia-probe.org",
    cache_ttl_hours=24: CrossValidatorBackend(
        email=email, cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"email": "noreply@aletheia-probe.org", "cache_ttl_hours": 24},
)
