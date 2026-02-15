# SPDX-License-Identifier: MIT
"""Cross-validation validators for backend pairs."""

from datetime import datetime
from typing import Any

from ..constants import CONFIDENCE_THRESHOLD_LOW
from ..logging_config import get_detail_logger, get_status_logger
from ..models import BackendResult, BackendStatus
from .protocols import CrossValidationCapable


status_logger = get_status_logger()


# Constants for cross-validation logic (from original cross_validator.py)
SINGLE_SOURCE_CONFIDENCE_PENALTY = 0.8
AGREEMENT_BONUS = 0.15
DISAGREEMENT_PENALTY = 0.7
CONFIDENCE_DISCREPANCY_THRESHOLD = 1.2

# Consistency check thresholds
PUB_VOLUME_CONSISTENCY_THRESHOLD_HIGH = 0.7
PUB_VOLUME_CONSISTENCY_THRESHOLD_LOW = 0.3
MINIMUM_LICENSE_SCORE = 50
RECENT_ACTIVITY_YEARS_THRESHOLD = 2
INACTIVE_ACTIVITY_YEARS_THRESHOLD = 3


def _format_assessment_label(assessment: Any | None) -> str:
    """Format backend assessment for human-readable reasoning output."""
    if assessment is None:
        return "None"
    value = getattr(assessment, "value", None)
    if isinstance(value, str):
        return value.upper()
    return str(assessment)


class OpenAlexCrossRefValidator:
    """Validator for OpenAlex and CrossRef backend pair.

    Implements CrossValidationCapable protocol for consistency checking
    between OpenAlex and CrossRef data sources.
    """

    def __init__(self) -> None:
        """Initialize the OpenAlex/CrossRef validator."""
        self.detail_logger = get_detail_logger()

    @property
    def supported_backend_pair(self) -> tuple[str, str]:
        """Get the backend pair this validator supports."""
        return ("openalex_analyzer", "crossref_analyzer")

    def validate(
        self, result1: BackendResult, result2: BackendResult
    ) -> dict[str, Any]:
        """Cross-validate OpenAlex and CrossRef results.

        Args:
            result1: Result from first backend (OpenAlex or CrossRef)
            result2: Result from second backend (CrossRef or OpenAlex)

        Returns:
            Cross-validation result dictionary with confidence adjustments
        """
        # Determine which result is from which backend
        if result1.backend_name == "openalex_analyzer":
            openalex_result, crossref_result = result1, result2
        else:
            openalex_result, crossref_result = result2, result1

        return self._cross_validate_results(openalex_result, crossref_result)

    def _cross_validate_results(
        self, openalex_result: BackendResult, crossref_result: BackendResult
    ) -> dict[str, Any]:
        """Orchestrate the cross-validation logic between OpenAlex and CrossRef results."""
        openalex_found = openalex_result.status == BackendStatus.FOUND
        crossref_found = crossref_result.status == BackendStatus.FOUND

        self.detail_logger.debug(
            f"Cross-validation - OpenAlex found: {openalex_found}, CrossRef found: {crossref_found}"
        )

        openalex_data = (
            openalex_result.data.get("openalex_data", {}) if openalex_found else {}
        )
        crossref_data = (
            crossref_result.data.get("crossref_data", {}) if crossref_found else {}
        )

        # Collect flags from both backends
        combined_flags = self._collect_combined_flags(
            openalex_result, crossref_result, openalex_found, crossref_found
        )

        # Perform consistency checks if both backends found data
        consistency_checks = []
        if openalex_found and crossref_found:
            consistency_checks = self._perform_consistency_checks(
                openalex_data, crossref_data
            )

        # Handle different scenarios
        if not openalex_found and not crossref_found:
            return {
                "confidence_adjustment": 0.0,
                "consistency_checks": [],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Journal not found in either OpenAlex or CrossRef databases"
                ],
                "agreement": False,
            }

        if openalex_found and not crossref_found:
            return self._handle_single_backend_result(
                openalex_result, "OpenAlex", "CrossRef", combined_flags
            )

        if crossref_found and not openalex_found:
            return self._handle_single_backend_result(
                crossref_result, "CrossRef", "OpenAlex", combined_flags
            )

        # Both backends found data - perform full cross-validation
        return self._combine_assessments(
            openalex_result, crossref_result, consistency_checks, combined_flags
        )

    def _collect_combined_flags(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        openalex_found: bool,
        crossref_found: bool,
    ) -> dict[str, list[str]]:
        """Collect and combine red and green flags from both backends."""
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
                [f"CrossRef: {flag}" for flag in crossref_analysis.get("red_flags", [])]
            )
            combined_flags["green_flags"].extend(
                [
                    f"CrossRef: {flag}"
                    for flag in crossref_analysis.get("green_flags", [])
                ]
            )

        return combined_flags

    def _handle_single_backend_result(
        self,
        result: BackendResult,
        backend_name: str,
        other_backend_name: str,
        combined_flags: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Create a validation result when only one backend returned data."""
        return {
            "confidence_adjustment": SINGLE_SOURCE_CONFIDENCE_PENALTY
            - 1.0,  # Negative adjustment
            "consistency_checks": [
                f"Only found in {backend_name}, not in {other_backend_name}"
            ],
            "combined_flags": combined_flags,
            "reasoning": [
                f"Assessment based solely on {backend_name} data",
                "Confidence reduced due to lack of cross-validation",
            ]
            + result.data.get("analysis", {}).get("reasoning", []),
            "agreement": False,
        }

    def _perform_consistency_checks(
        self, openalex_data: dict[str, Any], crossref_data: dict[str, Any]
    ) -> list[str]:
        """Perform data consistency checks between OpenAlex and CrossRef data."""
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
                    f"✓ Publisher names consistent: '{openalex_data.get('publisher')}' (OpenAlex) matches '{crossref_data.get('publisher')}' (CrossRef)"
                )
            else:
                checks.append(
                    f"⚠️ Publisher name mismatch: '{openalex_data.get('publisher')}' (OpenAlex) vs '{crossref_data.get('publisher')}' (CrossRef)"
                )

        # Check DOAJ listing consistency
        openalex_in_doaj = openalex_data.get("is_in_doaj", False)
        # CrossRef doesn't directly track DOAJ, but we can infer from license practices
        crossref_metrics = crossref_data.get("coverage", {})
        crossref_license_score = crossref_metrics.get("licenses", 0)

        if openalex_in_doaj:
            if crossref_license_score >= MINIMUM_LICENSE_SCORE:
                checks.append(
                    "✓ DOAJ listing consistent: Listed in DOAJ and good license reporting in CrossRef"
                )
            else:
                checks.append(
                    "⚠️ DOAJ inconsistency: Listed in DOAJ but poor license reporting in CrossRef"
                )

        # Check publication volume correlation
        openalex_total = openalex_data.get("total_publications", 0)
        crossref_total = crossref_data.get("counts", {}).get("total-dois", 0)

        if openalex_total > 0 and crossref_total > 0:
            ratio = min(openalex_total, crossref_total) / max(
                openalex_total, crossref_total
            )
            if (
                ratio >= PUB_VOLUME_CONSISTENCY_THRESHOLD_HIGH
            ):  # Within 30% of each other
                checks.append(
                    f"✓ Publication volumes consistent: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (CrossRef)"
                )
            elif ratio >= PUB_VOLUME_CONSISTENCY_THRESHOLD_LOW:
                checks.append(
                    f"⚠️ Moderate publication volume difference: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (CrossRef)"
                )
            else:
                checks.append(
                    f"⚠️ Large publication volume discrepancy: {openalex_total:,} (OpenAlex) vs {crossref_total:,} (CrossRef)"
                )

        # Check activity timeline consistency
        openalex_last_year = openalex_data.get("last_publication_year")
        crossref_current_dois = crossref_data.get("counts", {}).get("current-dois", 0)

        if openalex_last_year and crossref_current_dois:
            current_year = datetime.now().year
            if (
                openalex_last_year >= current_year - RECENT_ACTIVITY_YEARS_THRESHOLD
                and crossref_current_dois > 0
            ):
                checks.append("✓ Recent activity consistent in both databases")
            elif (
                openalex_last_year < current_year - INACTIVE_ACTIVITY_YEARS_THRESHOLD
                and crossref_current_dois == 0
            ):
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

    def _combine_assessments(
        self,
        openalex_result: BackendResult,
        crossref_result: BackendResult,
        consistency_checks: list[str],
        combined_flags: dict[str, Any],
    ) -> dict[str, Any]:
        """Combine individual backend assessments into a final result."""
        openalex_assessment = openalex_result.assessment
        crossref_assessment = crossref_result.assessment
        openalex_confidence = openalex_result.confidence
        crossref_confidence = crossref_result.confidence

        # Determine agreement and confidence adjustment
        agreement_bonus = 0.0
        assessment_agreement = False
        confidence_adjustment = 0.0

        if (
            openalex_assessment == crossref_assessment
            and openalex_assessment is not None
        ):
            # Both backends agree
            agreement_bonus = AGREEMENT_BONUS
            assessment_agreement = True
            confidence_adjustment = agreement_bonus
        elif (
            openalex_assessment is not None
            and crossref_assessment is not None
            and openalex_assessment != crossref_assessment
        ):
            # Disagreement - apply penalty
            if (
                openalex_confidence
                > crossref_confidence * CONFIDENCE_DISCREPANCY_THRESHOLD
            ):
                confidence_adjustment = (
                    DISAGREEMENT_PENALTY - 1.0
                )  # Negative adjustment
            elif (
                crossref_confidence
                > openalex_confidence * CONFIDENCE_DISCREPANCY_THRESHOLD
            ):
                confidence_adjustment = (
                    DISAGREEMENT_PENALTY - 1.0
                )  # Negative adjustment
            else:
                # Similar confidence but different assessments
                confidence_adjustment = CONFIDENCE_THRESHOLD_LOW - max(
                    openalex_confidence, crossref_confidence
                )  # Reduce to low threshold

        self.detail_logger.debug(
            f"Assessment agreement: {assessment_agreement}, "
            f"Confidence adjustment: {confidence_adjustment:+.3f}"
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            assessment_agreement,
            agreement_bonus,
            openalex_assessment,
            crossref_assessment,
            consistency_checks,
            openalex_result,
            crossref_result,
        )

        return {
            "confidence_adjustment": confidence_adjustment,
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

    def _generate_reasoning(
        self,
        assessment_agreement: bool,
        agreement_bonus: float,
        openalex_assessment: Any,
        crossref_assessment: Any,
        consistency_checks: list[str],
        openalex_result: BackendResult,
        crossref_result: BackendResult,
    ) -> list[str]:
        """Generate combined reasoning for the cross-validation result."""
        reasoning = []
        openalex_label = (
            openalex_assessment.value.upper()
            if hasattr(openalex_assessment, "value")
            else str(openalex_assessment)
        )
        crossref_label = (
            crossref_assessment.value.upper()
            if hasattr(crossref_assessment, "value")
            else str(crossref_assessment)
        )

        if assessment_agreement:
            reasoning.append(
                f"Both OpenAlex and CrossRef analysis agree: {openalex_label or crossref_label}"
            )
            reasoning.append(
                f"Cross-validation confidence bonus: +{agreement_bonus:.0%}"
            )
        elif (
            openalex_assessment is not None
            and crossref_assessment is not None
            and openalex_assessment != crossref_assessment
        ):
            reasoning.append(
                f"Backend disagreement: OpenAlex='{openalex_label}', CrossRef='{crossref_label}'"
            )
            reasoning.append("Confidence reduced due to disagreement")

        if consistency_checks:
            reasoning.extend(
                [f"Consistency check: {check}" for check in consistency_checks]
            )

        # Add summaries from individual backends
        if openalex_result.data.get("analysis", {}).get("reasoning"):
            reasoning.append("OpenAlex reasoning:")
            reasoning.extend(
                [f"  {r}" for r in openalex_result.data["analysis"]["reasoning"][:3]]
            )

        if crossref_result.data.get("analysis", {}).get("reasoning"):
            reasoning.append("CrossRef reasoning:")
            reasoning.extend(
                [f"  {r}" for r in crossref_result.data["analysis"]["reasoning"][:3]]
            )

        return reasoning


# Ensure OpenAlexCrossRefValidator implements the protocol
assert isinstance(OpenAlexCrossRefValidator(), CrossValidationCapable)


def _collect_backend_flags(
    backend_label: str, result: BackendResult
) -> dict[str, list[str]]:
    """Collect prefixed red/green flags from a backend analysis payload."""
    analysis = result.data.get("analysis", {})
    red_flags = analysis.get("red_flags", [])
    green_flags = analysis.get("green_flags", [])

    return {
        "red_flags": [f"{backend_label}: {flag}" for flag in red_flags],
        "green_flags": [f"{backend_label}: {flag}" for flag in green_flags],
    }


def _combine_pair_assessments(
    result_a: BackendResult,
    result_b: BackendResult,
) -> tuple[bool, float]:
    """Calculate agreement and confidence adjustment for two backend results."""
    assessment_a = result_a.assessment
    assessment_b = result_b.assessment

    if assessment_a == assessment_b and assessment_a is not None:
        return True, AGREEMENT_BONUS

    if (
        assessment_a is not None
        and assessment_b is not None
        and assessment_a != assessment_b
    ):
        confidence_a = result_a.confidence
        confidence_b = result_b.confidence

        if confidence_a > confidence_b * CONFIDENCE_DISCREPANCY_THRESHOLD:
            return False, DISAGREEMENT_PENALTY - 1.0
        if confidence_b > confidence_a * CONFIDENCE_DISCREPANCY_THRESHOLD:
            return False, DISAGREEMENT_PENALTY - 1.0
        return False, CONFIDENCE_THRESHOLD_LOW - max(confidence_a, confidence_b)

    return False, 0.0


class OpenAlexOpenCitationsValidator:
    """Validator for OpenAlex and OpenCitations backend pair."""

    def __init__(self) -> None:
        """Initialize validator."""
        self.detail_logger = get_detail_logger()

    @property
    def supported_backend_pair(self) -> tuple[str, str]:
        """Get supported backend pair."""
        return ("openalex_analyzer", "opencitations_analyzer")

    def validate(
        self, result1: BackendResult, result2: BackendResult
    ) -> dict[str, Any]:
        """Cross-validate OpenAlex and OpenCitations results."""
        if result1.backend_name == "openalex_analyzer":
            openalex_result, opencitations_result = result1, result2
        else:
            openalex_result, opencitations_result = result2, result1

        openalex_found = openalex_result.status == BackendStatus.FOUND
        opencitations_found = opencitations_result.status == BackendStatus.FOUND

        combined_flags: dict[str, list[str]] = {"red_flags": [], "green_flags": []}
        combined_flags["red_flags"].extend(
            _collect_backend_flags("OpenAlex", openalex_result)["red_flags"]
        )
        combined_flags["green_flags"].extend(
            _collect_backend_flags("OpenAlex", openalex_result)["green_flags"]
        )
        combined_flags["red_flags"].extend(
            _collect_backend_flags("OpenCitations", opencitations_result)["red_flags"]
        )
        combined_flags["green_flags"].extend(
            _collect_backend_flags("OpenCitations", opencitations_result)["green_flags"]
        )

        if not openalex_found or not opencitations_found:
            return {
                "confidence_adjustment": 0.0,
                "consistency_checks": [],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Cross-validation skipped: OpenAlex/OpenCitations data not available from both backends"
                ],
                "agreement": False,
            }

        openalex_data = openalex_result.data.get("openalex_data", {})
        opencitations_data = opencitations_result.data.get("opencitations_data", {})

        checks: list[str] = []
        openalex_citations = openalex_data.get("cited_by_count", 0)
        opencitations_citations = opencitations_data.get("citation_count", 0)
        if openalex_citations > 0 and opencitations_citations > 0:
            ratio = min(openalex_citations, opencitations_citations) / max(
                openalex_citations, opencitations_citations
            )
            if ratio >= PUB_VOLUME_CONSISTENCY_THRESHOLD_LOW:
                checks.append(
                    "✓ Citation footprint broadly consistent between OpenAlex and OpenCitations"
                )
            else:
                checks.append(
                    "⚠️ Citation footprint differs substantially between OpenAlex and OpenCitations"
                )

        agreement, confidence_adjustment = _combine_pair_assessments(
            openalex_result, opencitations_result
        )
        openalex_label = _format_assessment_label(openalex_result.assessment)
        opencitations_label = _format_assessment_label(opencitations_result.assessment)

        reasoning = []
        if agreement:
            reasoning.append(
                f"Both OpenAlex and OpenCitations analysis agree: {openalex_label}"
            )
        elif (
            openalex_result.assessment is not None
            and opencitations_result.assessment is not None
            and openalex_result.assessment != opencitations_result.assessment
        ):
            reasoning.append(
                "Backend disagreement: "
                f"OpenAlex='{openalex_label}', OpenCitations='{opencitations_label}'"
            )
            reasoning.append("Confidence reduced due to disagreement")

        if checks:
            reasoning.extend([f"Consistency check: {check}" for check in checks])

        return {
            "confidence_adjustment": confidence_adjustment,
            "consistency_checks": checks,
            "combined_flags": combined_flags,
            "reasoning": reasoning,
            "agreement": agreement,
        }


class CrossRefOpenCitationsValidator:
    """Validator for CrossRef and OpenCitations backend pair."""

    def __init__(self) -> None:
        """Initialize validator."""
        self.detail_logger = get_detail_logger()

    @property
    def supported_backend_pair(self) -> tuple[str, str]:
        """Get supported backend pair."""
        return ("crossref_analyzer", "opencitations_analyzer")

    def validate(
        self, result1: BackendResult, result2: BackendResult
    ) -> dict[str, Any]:
        """Cross-validate CrossRef and OpenCitations results."""
        if result1.backend_name == "crossref_analyzer":
            crossref_result, opencitations_result = result1, result2
        else:
            crossref_result, opencitations_result = result2, result1

        crossref_found = crossref_result.status == BackendStatus.FOUND
        opencitations_found = opencitations_result.status == BackendStatus.FOUND

        combined_flags: dict[str, list[str]] = {"red_flags": [], "green_flags": []}
        combined_flags["red_flags"].extend(
            _collect_backend_flags("CrossRef", crossref_result)["red_flags"]
        )
        combined_flags["green_flags"].extend(
            _collect_backend_flags("CrossRef", crossref_result)["green_flags"]
        )
        combined_flags["red_flags"].extend(
            _collect_backend_flags("OpenCitations", opencitations_result)["red_flags"]
        )
        combined_flags["green_flags"].extend(
            _collect_backend_flags("OpenCitations", opencitations_result)["green_flags"]
        )

        if not crossref_found or not opencitations_found:
            return {
                "confidence_adjustment": 0.0,
                "consistency_checks": [],
                "combined_flags": combined_flags,
                "reasoning": [
                    "Cross-validation skipped: CrossRef/OpenCitations data not available from both backends"
                ],
                "agreement": False,
            }

        crossref_data = crossref_result.data.get("crossref_data", {})
        opencitations_data = opencitations_result.data.get("opencitations_data", {})

        checks: list[str] = []
        crossref_total_dois = crossref_data.get("counts", {}).get("total-dois", 0)
        opencitations_references = opencitations_data.get("reference_count", 0)
        if crossref_total_dois > 0 and opencitations_references > 0:
            ratio = min(crossref_total_dois, opencitations_references) / max(
                crossref_total_dois, opencitations_references
            )
            if ratio >= PUB_VOLUME_CONSISTENCY_THRESHOLD_LOW:
                checks.append(
                    "✓ CrossRef DOI volume and OpenCitations reference footprint are broadly consistent"
                )
            else:
                checks.append(
                    "⚠️ CrossRef DOI volume and OpenCitations reference footprint differ substantially"
                )

        agreement, confidence_adjustment = _combine_pair_assessments(
            crossref_result, opencitations_result
        )
        crossref_label = _format_assessment_label(crossref_result.assessment)
        opencitations_label = _format_assessment_label(opencitations_result.assessment)

        reasoning = []
        if agreement:
            reasoning.append(
                f"Both CrossRef and OpenCitations analysis agree: {crossref_label}"
            )
        elif (
            crossref_result.assessment is not None
            and opencitations_result.assessment is not None
            and crossref_result.assessment != opencitations_result.assessment
        ):
            reasoning.append(
                "Backend disagreement: "
                f"CrossRef='{crossref_label}', OpenCitations='{opencitations_label}'"
            )
            reasoning.append("Confidence reduced due to disagreement")

        if checks:
            reasoning.extend([f"Consistency check: {check}" for check in checks])

        return {
            "confidence_adjustment": confidence_adjustment,
            "consistency_checks": checks,
            "combined_flags": combined_flags,
            "reasoning": reasoning,
            "agreement": agreement,
        }


# Ensure validators implement protocol
assert isinstance(OpenAlexOpenCitationsValidator(), CrossValidationCapable)
assert isinstance(CrossRefOpenCitationsValidator(), CrossValidationCapable)
