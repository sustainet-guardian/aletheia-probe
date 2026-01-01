# SPDX-License-Identifier: MIT
"""Risk level calculation utilities for retraction data."""

from .constants import RETRACTION_THRESHOLDS
from .enums import RiskLevel


def calculate_retraction_risk_level(
    total_retractions: int,
    recent_retractions: int,
    total_publications: int | None = None,
    recent_publications: int | None = None,
) -> RiskLevel:
    """
    Calculate retraction risk level and classification.

    Uses rate-based thresholds when publication data is available,
    falls back to absolute count thresholds otherwise.

    Research shows average retraction rate: ~0.02-0.04%
    Rate-based thresholds are more accurate for journals with different publication volumes.

    Args:
        total_retractions: Total number of retractions
        recent_retractions: Number of retractions in recent period (typically last 2-5 years)
        total_publications: Total number of articles published (optional)
        recent_publications: Number of articles in recent period (optional)

    Returns:
        Risk level classification:
        - "none": No retractions
        - "note": Has retractions but within normal range
        - "low": Elevated retraction rate (2-3x normal)
        - "moderate": Concerning retraction rate (5x normal)
        - "high": High retraction rate (10x normal)
        - "critical": Very high retraction rate (25x+ normal)

    Examples:
        >>> calculate_retraction_risk_level(0, 0)
        'none'
        >>> calculate_retraction_risk_level(2, 1)
        'low'
        >>> calculate_retraction_risk_level(50, 20, 5000, 1000)
        'high'
    """
    # No retractions
    if total_retractions == 0:
        return RiskLevel.NONE

    # Rate-based thresholds when publication data is available
    if total_publications and total_publications > 0:
        overall_rate = (total_retractions / total_publications) * 100  # Percentage

        # Calculate recent rate
        recent_rate = 0.0
        if recent_publications and recent_publications > 0:
            recent_rate = (recent_retractions / recent_publications) * 100

        # Use either overall OR recent rate to flag issues
        # Thresholds are percentage values
        if (
            overall_rate >= RETRACTION_THRESHOLDS.rate_critical
            or recent_rate >= RETRACTION_THRESHOLDS.recent_rate_critical
        ):
            return RiskLevel.CRITICAL  # Very high rate (25x+ normal)
        elif (
            overall_rate >= RETRACTION_THRESHOLDS.rate_high
            or recent_rate >= RETRACTION_THRESHOLDS.recent_rate_high
        ):
            return RiskLevel.HIGH  # High rate (10x normal)
        elif (
            overall_rate >= RETRACTION_THRESHOLDS.rate_moderate
            or recent_rate >= RETRACTION_THRESHOLDS.recent_rate_moderate
        ):
            return RiskLevel.MODERATE  # Moderate rate (5x normal)
        elif (
            overall_rate >= RETRACTION_THRESHOLDS.rate_low
            or recent_rate >= RETRACTION_THRESHOLDS.recent_rate_low
        ):
            return RiskLevel.LOW  # Elevated rate (2-3x normal)
        elif total_retractions > 0:
            return RiskLevel.NOTE  # Within normal range but some retractions exist
        else:
            return RiskLevel.NONE

    # Fallback to absolute counts if no publication data
    # Based on analysis of retraction data patterns
    if (
        total_retractions >= RETRACTION_THRESHOLDS.count_critical
        or recent_retractions >= RETRACTION_THRESHOLDS.recent_count_critical
    ):
        return RiskLevel.CRITICAL
    elif (
        total_retractions >= RETRACTION_THRESHOLDS.count_high
        or recent_retractions >= RETRACTION_THRESHOLDS.recent_count_high
    ):
        return RiskLevel.HIGH
    elif (
        total_retractions >= RETRACTION_THRESHOLDS.count_moderate
        or recent_retractions >= RETRACTION_THRESHOLDS.recent_count_moderate
    ):
        return RiskLevel.MODERATE
    elif total_retractions >= RETRACTION_THRESHOLDS.count_low:
        return RiskLevel.LOW
    else:
        return RiskLevel.NOTE
