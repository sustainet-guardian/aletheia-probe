# SPDX-License-Identifier: MIT
"""Cross-validation backend that combines OpenAlex and Crossref analysis."""

import asyncio
import time
from typing import Any

from ..models import BackendResult, BackendStatus, QueryInput
from .base import Backend, get_backend_registry
from .crossref_analyzer import CrossrefAnalyzerBackend
from .openalex_analyzer import OpenAlexAnalyzerBackend


class CrossValidatorBackend(Backend):
    """Backend that combines and cross-validates OpenAlex and Crossref data."""

    def __init__(
        self, email: str = "noreply.aletheia-probe.org", cache_ttl_hours: int = 24
    ):
        """Initialize cross-validation backend.

        Args:
            email: Email for API access
            cache_ttl_hours: Cache TTL in hours
        """
        super().__init__(cache_ttl_hours)
        self.openalex_backend = OpenAlexAnalyzerBackend(email, cache_ttl_hours)
        self.crossref_backend = CrossrefAnalyzerBackend(email, cache_ttl_hours)

    def get_name(self) -> str:
        """Return backend name."""
        return "cross_validator"

    def get_description(self) -> str:
        """Return backend description."""
        return "Cross-validates assessments between OpenAlex and Crossref data sources"

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Query both backends and cross-validate results."""
        start_time = time.time()

        try:
            # Query both backends concurrently
            openalex_result, crossref_result = await asyncio.gather(
                self.openalex_backend.query(query_input),
                self.crossref_backend.query(query_input),
                return_exceptions=True,
            )

            response_time = time.time() - start_time

            # Handle exceptions
            if isinstance(openalex_result, Exception):
                openalex_result = BackendResult(
                    backend_name=self.openalex_backend.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=str(openalex_result),
                    response_time=0.0,
                )

            if isinstance(crossref_result, Exception):
                crossref_result = BackendResult(
                    backend_name=self.crossref_backend.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment=None,
                    error_message=str(crossref_result),
                    response_time=0.0,
                )

            # Perform cross-validation analysis (check for errors first)
            if isinstance(openalex_result, BaseException) or isinstance(
                crossref_result, BaseException
            ):
                return BackendResult(
                    backend_name=self.get_name(),
                    status=BackendStatus.ERROR,
                    confidence=0.0,
                    assessment="insufficient_data",
                    data={},
                    sources=[],
                    error_message="Backend error during cross-validation",
                    response_time=response_time,
                )

            validation_result = self._cross_validate_results(
                openalex_result, crossref_result, query_input
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
            )

        except Exception as e:
            response_time = time.time() - start_time
            return BackendResult(
                backend_name=self.get_name(),
                status=BackendStatus.ERROR,
                confidence=0.0,
                assessment=None,
                error_message=str(e),
                response_time=response_time,
            )

    def _cross_validate_results(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        query_input: QueryInput,
    ) -> dict[str, Any]:
        """Cross-validate results from both backends."""

        # Check if both backends found data
        openalex_found = openalex_result.status == BackendStatus.FOUND
        crossref_found = crossref_result.status == BackendStatus.FOUND

        # Extract data for comparison
        openalex_data = (
            openalex_result.data.get("openalex_data", {}) if openalex_found else {}
        )
        crossref_data = (
            crossref_result.data.get("crossref_data", {}) if crossref_found else {}
        )

        # Collect all red and green flags
        combined_flags: dict[str, list[str]] = {
            "red_flags": [],
            "green_flags": [],
        }

        consistency_checks = []

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

        # Cross-validation checks
        if openalex_found and crossref_found:
            consistency_checks = self._perform_consistency_checks(
                openalex_data, crossref_data, query_input
            )

        # Determine final assessment
        if not openalex_found and not crossref_found:
            return {
                "status": BackendStatus.NOT_FOUND,
                "assessment": None,
                "confidence": 0.0,
                "consistency_checks": [],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Journal not found in either OpenAlex or Crossref databases"
                ],
            }

        # If only one backend found data, use that result but with reduced confidence
        if openalex_found and not crossref_found:
            return {
                "status": BackendStatus.FOUND,
                "assessment": openalex_result.assessment,
                "confidence": max(
                    0.1, openalex_result.confidence * 0.8
                ),  # Reduce confidence for single source
                "consistency_checks": ["Only found in OpenAlex, not in Crossref"],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Assessment based solely on OpenAlex data",
                    "Confidence reduced due to lack of cross-validation",
                ]
                + openalex_result.data.get("analysis", {}).get("reasoning", []),
            }

        if crossref_found and not openalex_found:
            return {
                "status": BackendStatus.FOUND,
                "assessment": crossref_result.assessment,
                "confidence": max(
                    0.1, crossref_result.confidence * 0.8
                ),  # Reduce confidence for single source
                "consistency_checks": ["Only found in Crossref, not in OpenAlex"],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Assessment based solely on Crossref data",
                    "Confidence reduced due to lack of cross-validation",
                ]
                + crossref_result.data.get("analysis", {}).get("reasoning", []),
            }

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

        return checks

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

        # Agreement bonus for consistent assessments
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
            base_confidence = (
                crossref_confidence * 0.9
            )  # Slight reduction for partial data
        elif crossref_assessment is None and openalex_assessment is not None:
            # Only OpenAlex has an assessment
            final_assessment = openalex_assessment
            base_confidence = (
                openalex_confidence * 0.9
            )  # Slight reduction for partial data
        elif openalex_assessment != crossref_assessment:
            # Disagreement between backends
            if openalex_confidence > crossref_confidence * 1.2:
                final_assessment = openalex_assessment or "insufficient_data"
                base_confidence = (
                    openalex_confidence * 0.7
                )  # Reduce confidence for disagreement
            elif crossref_confidence > openalex_confidence * 1.2:
                final_assessment = crossref_assessment or "insufficient_data"
                base_confidence = (
                    crossref_confidence * 0.7
                )  # Reduce confidence for disagreement
            else:
                # Confidence levels are similar but assessments disagree - inconclusive
                final_assessment = None
                base_confidence = 0.3
        else:
            # Both backends returned None assessment
            final_assessment = None
            base_confidence = 0.2

        # Apply agreement bonus
        final_confidence = min(1.0, base_confidence + agreement_bonus)

        # Consistency check adjustments
        warning_count = sum(1 for check in consistency_checks if "⚠️" in check)
        success_count = sum(1 for check in consistency_checks if "✓" in check)

        if warning_count >= 2:
            final_confidence = max(
                0.1, final_confidence - 0.1
            )  # Reduce for multiple inconsistencies
        elif success_count >= 2:
            final_confidence = min(
                1.0, final_confidence + 0.05
            )  # Small boost for consistency

        # Generate reasoning
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
            )  # Top 3

        if crossref_result.data.get("analysis", {}).get("reasoning"):
            reasoning.append("Crossref reasoning:")
            reasoning.extend(
                [f"  {r}" for r in crossref_result.data["analysis"]["reasoning"][:3]]
            )  # Top 3

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
    lambda email="noreply.aletheia-probe.org",
    cache_ttl_hours=24: CrossValidatorBackend(
        email=email, cache_ttl_hours=cache_ttl_hours
    ),
    default_config={"email": "noreply.aletheia-probe.org", "cache_ttl_hours": 24},
)
