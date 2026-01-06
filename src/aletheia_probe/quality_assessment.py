# SPDX-License-Identifier: MIT
"""Quality assessment processor for backend results.

This module provides processing for quality indicator backends that provide
metrics like retraction data, citation patterns, etc.
"""

from typing import Any

from aletheia_probe.enums import EvidenceType
from aletheia_probe.models import BackendResult, BackendStatus


class QualityAssessmentProcessor:
    """Process quality assessment data from backend results.

    This processor extracts data from backends that provide quality indicators
    (like retraction data) and formats them for use in final assessments.
    Uses evidence type classification, not backend names.
    """

    def extract_quality_data(
        self, backend_results: list[BackendResult], reasoning: list[str]
    ) -> dict[str, Any]:
        """Extract quality indicator data from backend results.

        Searches for backends with QUALITY_INDICATOR evidence type and
        extracts their data. Formats reasoning messages based on risk levels.

        Args:
            backend_results: List of all backend results
            reasoning: List to append reasoning messages to

        Returns:
            Dictionary with quality data including risk_level and total_retractions
        """
        # Find quality indicator backends (generic, not name-specific)
        quality_result = next(
            (
                r
                for r in backend_results
                if r.evidence_type == EvidenceType.QUALITY_INDICATOR.value
                and r.status == BackendStatus.FOUND
            ),
            None,
        )

        if not quality_result or not quality_result.data:
            return {}

        # Extract common quality fields (structure depends on backend implementation)
        quality_data = quality_result.data
        risk_level = quality_data.get("risk_level")
        total_retractions = quality_data.get("total_retractions", 0)
        recent_retractions = quality_data.get("recent_retractions", 0)
        has_publication_data = quality_data.get("has_publication_data", False)
        retraction_rate = quality_data.get("retraction_rate")
        total_publications = quality_data.get("total_publications")

        # Format reasoning messages based on risk level
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
