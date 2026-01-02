# SPDX-License-Identifier: MIT
"""Unit tests for risk_calculator.py retraction risk level calculations."""

import pytest

from aletheia_probe.enums import RiskLevel
from aletheia_probe.risk_calculator import calculate_retraction_risk_level


class TestCalculateRetractionRiskLevel:
    """Test suite for calculate_retraction_risk_level function."""

    def test_no_retractions_returns_none_level(self) -> None:
        """Test that zero retractions always returns NONE risk level."""
        # No retractions at all
        assert calculate_retraction_risk_level(0, 0) == RiskLevel.NONE
        assert calculate_retraction_risk_level(0, 0, 1000, 500) == RiskLevel.NONE

    def test_rate_based_calculation_critical_level(self) -> None:
        """Test critical risk level with rate-based calculations."""
        # Critical overall rate (3.0% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=30,
                recent_retractions=5,
                total_publications=1000,
                recent_publications=200,
            )
            == RiskLevel.CRITICAL
        )

        # Critical recent rate (4.0% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=5,
                recent_retractions=20,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.CRITICAL
        )

    def test_rate_based_calculation_high_level(self) -> None:
        """Test high risk level with rate-based calculations."""
        # High overall rate (1.5% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=15,
                recent_retractions=5,
                total_publications=1000,
                recent_publications=200,
            )
            == RiskLevel.HIGH
        )

        # High recent rate (2.5% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=5,
                recent_retractions=13,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )

    def test_rate_based_calculation_moderate_level(self) -> None:
        """Test moderate risk level with rate-based calculations."""
        # Moderate overall rate (0.8% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=8,
                recent_retractions=2,
                total_publications=1000,
                recent_publications=200,
            )
            == RiskLevel.MODERATE
        )

        # Moderate recent rate (1.2% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=2,
                recent_retractions=6,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.MODERATE
        )

    def test_rate_based_calculation_low_level(self) -> None:
        """Test low risk level with rate-based calculations."""
        # Low overall rate (0.1% threshold)
        assert (
            calculate_retraction_risk_level(
                total_retractions=1,
                recent_retractions=0,
                total_publications=1000,
                recent_publications=200,
            )
            == RiskLevel.LOW
        )

        # Low recent rate (0.2% threshold)
        # Note: total_retractions must be > 0 for function to not exit early
        assert (
            calculate_retraction_risk_level(
                total_retractions=1,
                recent_retractions=1,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.LOW
        )

    def test_rate_based_calculation_note_level(self) -> None:
        """Test note level when retractions exist but rates are within normal range."""
        # Very low rates but some retractions exist
        assert (
            calculate_retraction_risk_level(
                total_retractions=1,
                recent_retractions=0,
                total_publications=10000,
                recent_publications=5000,
            )
            == RiskLevel.NOTE
        )

    def test_absolute_count_fallback_critical_level(self) -> None:
        """Test critical risk level using absolute count fallback."""
        # Critical total count (21+ threshold)
        assert calculate_retraction_risk_level(21, 5) == RiskLevel.CRITICAL
        assert calculate_retraction_risk_level(25, 8) == RiskLevel.CRITICAL

        # Critical recent count (10+ threshold)
        assert calculate_retraction_risk_level(15, 10) == RiskLevel.CRITICAL
        assert calculate_retraction_risk_level(5, 12) == RiskLevel.CRITICAL

    def test_absolute_count_fallback_high_level(self) -> None:
        """Test high risk level using absolute count fallback."""
        # High total count (11+ threshold)
        assert calculate_retraction_risk_level(11, 2) == RiskLevel.HIGH
        assert calculate_retraction_risk_level(15, 3) == RiskLevel.HIGH

        # High recent count (5+ threshold)
        assert calculate_retraction_risk_level(8, 5) == RiskLevel.HIGH
        assert calculate_retraction_risk_level(4, 7) == RiskLevel.HIGH

    def test_absolute_count_fallback_moderate_level(self) -> None:
        """Test moderate risk level using absolute count fallback."""
        # Moderate total count (6+ threshold)
        assert calculate_retraction_risk_level(6, 1) == RiskLevel.MODERATE
        assert calculate_retraction_risk_level(8, 2) == RiskLevel.MODERATE

        # Moderate recent count (3+ threshold)
        assert calculate_retraction_risk_level(4, 3) == RiskLevel.MODERATE
        assert calculate_retraction_risk_level(2, 4) == RiskLevel.MODERATE

    def test_absolute_count_fallback_low_level(self) -> None:
        """Test low risk level using absolute count fallback."""
        # Low total count (2+ threshold)
        assert calculate_retraction_risk_level(2, 0) == RiskLevel.LOW
        assert calculate_retraction_risk_level(4, 1) == RiskLevel.LOW

    def test_absolute_count_fallback_note_level(self) -> None:
        """Test note level using absolute count fallback."""
        # Single retraction below low threshold
        assert calculate_retraction_risk_level(1, 0) == RiskLevel.NOTE
        assert calculate_retraction_risk_level(1, 1) == RiskLevel.NOTE

    def test_boundary_conditions_rate_based(self) -> None:
        """Test boundary conditions for rate-based thresholds."""
        # Test exact threshold values for overall rate

        # Just below critical (3.0%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=29,
                recent_retractions=5,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )

        # Exactly at critical (3.0%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=30,
                recent_retractions=5,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.CRITICAL
        )

        # Just below high (1.5%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=14,
                recent_retractions=2,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.MODERATE
        )

        # Exactly at high (1.5%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=15,
                recent_retractions=2,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )

    def test_boundary_conditions_recent_rate_based(self) -> None:
        """Test boundary conditions for recent rate-based thresholds."""
        # Test exact threshold values for recent rate

        # Just below critical recent rate (4.0%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=5,
                recent_retractions=19,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )

        # Exactly at critical recent rate (4.0%)
        assert (
            calculate_retraction_risk_level(
                total_retractions=5,
                recent_retractions=20,
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.CRITICAL
        )

    def test_boundary_conditions_absolute_counts(self) -> None:
        """Test boundary conditions for absolute count thresholds."""
        # Test exact threshold values for total count

        # Just below critical (21)
        assert calculate_retraction_risk_level(20, 5) == RiskLevel.HIGH

        # Exactly at critical (21)
        assert calculate_retraction_risk_level(21, 5) == RiskLevel.CRITICAL

        # Just below high (11)
        assert calculate_retraction_risk_level(10, 2) == RiskLevel.MODERATE

        # Exactly at high (11)
        assert calculate_retraction_risk_level(11, 2) == RiskLevel.HIGH

        # Just below moderate (6)
        assert calculate_retraction_risk_level(5, 1) == RiskLevel.LOW

        # Exactly at moderate (6)
        assert calculate_retraction_risk_level(6, 1) == RiskLevel.MODERATE

        # Just below low (2)
        assert calculate_retraction_risk_level(1, 0) == RiskLevel.NOTE

        # Exactly at low (2)
        assert calculate_retraction_risk_level(2, 0) == RiskLevel.LOW

    def test_recent_count_takes_priority(self) -> None:
        """Test that recent counts can trigger higher risk levels than total counts."""
        # Low total count but high recent count should trigger HIGH level
        assert calculate_retraction_risk_level(8, 5) == RiskLevel.HIGH

        # Moderate total count but critical recent count should trigger CRITICAL level
        assert calculate_retraction_risk_level(7, 10) == RiskLevel.CRITICAL

    def test_rate_takes_priority_over_counts(self) -> None:
        """Test that rate-based calculation takes priority over absolute counts."""
        # High absolute counts but low rate should use rate-based calculation
        assert (
            calculate_retraction_risk_level(
                total_retractions=25,  # Would be CRITICAL by count
                recent_retractions=10,  # Would be CRITICAL by recent count
                total_publications=100000,  # Very high publication volume
                recent_publications=50000,
            )
            == RiskLevel.NOTE
        )  # Low rate due to high publication volume

    def test_zero_publications_fallback_to_counts(self) -> None:
        """Test fallback to absolute counts when publications are zero."""
        assert calculate_retraction_risk_level(25, 10, 0, 0) == RiskLevel.CRITICAL
        assert calculate_retraction_risk_level(25, 10, None, 0) == RiskLevel.CRITICAL
        assert calculate_retraction_risk_level(25, 10, 0, None) == RiskLevel.CRITICAL

    def test_none_publications_fallback_to_counts(self) -> None:
        """Test fallback to absolute counts when publications are None."""
        assert calculate_retraction_risk_level(25, 10, None, None) == RiskLevel.CRITICAL
        assert calculate_retraction_risk_level(15, 5, None, 500) == RiskLevel.HIGH
        assert calculate_retraction_risk_level(15, 5, 1000, None) == RiskLevel.HIGH

    def test_recent_publications_without_recent_retractions(self) -> None:
        """Test handling when recent publications exist but recent_retractions is zero."""
        # Should still calculate overall rate properly
        assert (
            calculate_retraction_risk_level(
                total_retractions=30,
                recent_retractions=0,  # No recent retractions
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.CRITICAL
        )  # Based on overall rate

    def test_edge_case_single_publication(self) -> None:
        """Test edge case with very small publication numbers."""
        # Single publication with single retraction = 100% rate
        assert (
            calculate_retraction_risk_level(
                total_retractions=1,
                recent_retractions=0,
                total_publications=1,
                recent_publications=0,
            )
            == RiskLevel.CRITICAL
        )

        # Single recent publication with single recent retraction = 100% rate
        assert (
            calculate_retraction_risk_level(
                total_retractions=1,
                recent_retractions=1,
                total_publications=100,
                recent_publications=1,
            )
            == RiskLevel.CRITICAL
        )

    def test_high_publication_volume_low_risk(self) -> None:
        """Test that high publication volumes with few retractions result in low risk."""
        # Many publications, very few retractions
        assert (
            calculate_retraction_risk_level(
                total_retractions=5,
                recent_retractions=2,
                total_publications=50000,
                recent_publications=25000,
            )
            == RiskLevel.NOTE
        )

    def test_consistent_risk_escalation(self) -> None:
        """Test that risk levels escalate consistently with increasing retraction counts."""
        # Test progression with absolute counts
        assert calculate_retraction_risk_level(1, 0) == RiskLevel.NOTE
        assert calculate_retraction_risk_level(2, 0) == RiskLevel.LOW
        assert calculate_retraction_risk_level(6, 0) == RiskLevel.MODERATE
        assert calculate_retraction_risk_level(11, 0) == RiskLevel.HIGH
        assert calculate_retraction_risk_level(21, 0) == RiskLevel.CRITICAL

    def test_both_overall_and_recent_rate_triggering(self) -> None:
        """Test scenarios where both overall and recent rates could trigger different levels."""
        # Overall rate triggers MODERATE, recent rate triggers HIGH
        # Should return HIGH (recent takes priority when higher)
        assert (
            calculate_retraction_risk_level(
                total_retractions=8,  # 0.8% overall rate -> MODERATE
                recent_retractions=13,  # 2.6% recent rate -> HIGH
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )

        # Overall rate triggers HIGH, recent rate triggers MODERATE
        # Should return HIGH (overall takes priority when higher)
        assert (
            calculate_retraction_risk_level(
                total_retractions=16,  # 1.6% overall rate -> HIGH
                recent_retractions=5,  # 1.0% recent rate -> MODERATE
                total_publications=1000,
                recent_publications=500,
            )
            == RiskLevel.HIGH
        )
