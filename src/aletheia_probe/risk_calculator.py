# SPDX-License-Identifier: MIT
"""Risk level calculation utilities for retraction data."""

from dataclasses import dataclass

from .enums import RiskLevel


@dataclass(frozen=True)
class RetractionThresholds:
    """Thresholds for assessing retraction risk levels.

    Research shows average retraction rate: ~0.02-0.04%
    Unified thresholds balancing different implementations.
    """

    # Rate-based thresholds (percentage)
    rate_critical: float = 3.0  # Very high rate
    rate_high: float = 1.5  # High rate
    rate_moderate: float = 0.8  # Moderate rate
    rate_low: float = 0.1  # Elevated rate

    # Recent rate thresholds (percentage)
    recent_rate_critical: float = 4.0
    recent_rate_high: float = 2.5
    recent_rate_moderate: float = 1.2
    recent_rate_low: float = 0.2

    # Absolute count fallback thresholds
    count_critical: int = 21
    count_high: int = 11
    count_moderate: int = 6
    count_low: int = 2

    # Recent count fallback thresholds
    recent_count_critical: int = 10
    recent_count_high: int = 5
    recent_count_moderate: int = 3
    recent_count_low: int = 2


# Instance for use throughout the application
RETRACTION_THRESHOLDS = RetractionThresholds()

# Risk level thresholds ordered from highest to lowest severity
_RATE_THRESHOLDS: list[tuple[RiskLevel, float, float]] = [
    (
        RiskLevel.CRITICAL,
        RETRACTION_THRESHOLDS.rate_critical,
        RETRACTION_THRESHOLDS.recent_rate_critical,
    ),
    (
        RiskLevel.HIGH,
        RETRACTION_THRESHOLDS.rate_high,
        RETRACTION_THRESHOLDS.recent_rate_high,
    ),
    (
        RiskLevel.MODERATE,
        RETRACTION_THRESHOLDS.rate_moderate,
        RETRACTION_THRESHOLDS.recent_rate_moderate,
    ),
    (
        RiskLevel.LOW,
        RETRACTION_THRESHOLDS.rate_low,
        RETRACTION_THRESHOLDS.recent_rate_low,
    ),
]

_COUNT_THRESHOLDS: list[tuple[RiskLevel, int, int]] = [
    (
        RiskLevel.CRITICAL,
        RETRACTION_THRESHOLDS.count_critical,
        RETRACTION_THRESHOLDS.recent_count_critical,
    ),
    (
        RiskLevel.HIGH,
        RETRACTION_THRESHOLDS.count_high,
        RETRACTION_THRESHOLDS.recent_count_high,
    ),
    (
        RiskLevel.MODERATE,
        RETRACTION_THRESHOLDS.count_moderate,
        RETRACTION_THRESHOLDS.recent_count_moderate,
    ),
    (
        RiskLevel.LOW,
        RETRACTION_THRESHOLDS.count_low,
        RETRACTION_THRESHOLDS.recent_count_low,
    ),
]


def calculate_retraction_risk_level(
    total_retractions: int,
    recent_retractions: int,
    total_publications: int | None = None,
    recent_publications: int | None = None,
) -> RiskLevel:
    """Calculate retraction risk level and classification.

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
        RiskLevel: An enum member representing the calculated risk level.

    Examples:
        >>> from .enums import RiskLevel
        >>> calculate_retraction_risk_level(0, 0)
        <RiskLevel.NONE: 'none'>
        >>> calculate_retraction_risk_level(2, 1)
        <RiskLevel.LOW: 'low'>
        >>> calculate_retraction_risk_level(50, 20, 5000, 1000)
        <RiskLevel.HIGH: 'high'>
    """
    if total_retractions == 0:
        return RiskLevel.NONE

    # Rate-based thresholds when publication data is available
    if total_publications and total_publications > 0:
        overall_rate = (total_retractions / total_publications) * 100
        recent_rate = 0.0
        if recent_publications and recent_publications > 0:
            recent_rate = (recent_retractions / recent_publications) * 100

        for level, rate_threshold, recent_threshold in _RATE_THRESHOLDS:
            if overall_rate >= rate_threshold or recent_rate >= recent_threshold:
                return level
        return RiskLevel.NOTE

    # Fallback to absolute counts if no publication data
    for level, count_threshold, recent_threshold in _COUNT_THRESHOLDS:
        if (
            total_retractions >= count_threshold
            or recent_retractions >= recent_threshold
        ):
            return level
    return RiskLevel.NOTE
