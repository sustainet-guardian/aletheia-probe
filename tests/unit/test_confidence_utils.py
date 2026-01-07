# SPDX-License-Identifier: MIT
"""Tests for confidence scoring utilities."""

from aletheia_probe.confidence_utils import (
    MatchQuality,
    calculate_base_confidence,
    calculate_name_similarity,
    graduated_confidence,
)


class TestConfidenceUtils:
    """Tests for confidence utility functions."""

    def test_calculate_base_confidence(self) -> None:
        """Test base confidence mapping."""
        assert calculate_base_confidence(MatchQuality.EXACT_ISSN) == 1.0
        assert calculate_base_confidence(MatchQuality.EXACT_NAME) == 0.95
        assert calculate_base_confidence(MatchQuality.EXACT_ALIAS) == 0.90
        assert calculate_base_confidence(MatchQuality.SUBSTRING_MATCH) == 0.70
        assert calculate_base_confidence(MatchQuality.WORD_SIMILARITY) == 0.60
        assert calculate_base_confidence(MatchQuality.FUZZY_MATCH) == 0.50
        assert calculate_base_confidence(MatchQuality.NO_MATCH) == 0.0

    def test_calculate_name_similarity_exact(self) -> None:
        """Test exact name similarity."""
        score = calculate_name_similarity("Journal A", "Journal A")
        assert score == 1.0

        score = calculate_name_similarity("Journal A", "journal a")
        assert score == 1.0

    def test_calculate_name_similarity_jaccard(self) -> None:
        """Test Jaccard similarity."""
        # "Journal of Medicine" vs "Journal of Science"
        # {journal, of, medicine} vs {journal, of, science}
        # Intersection: {journal, of} (2)
        # Union: {journal, of, medicine, science} (4)
        # Score: 0.5
        score = calculate_name_similarity("Journal of Medicine", "Journal of Science")
        assert score == 0.5

    def test_calculate_name_similarity_empty(self) -> None:
        """Test empty strings."""
        assert calculate_name_similarity("", "Journal") == 0.0
        assert calculate_name_similarity("Journal", "") == 0.0

    def test_graduated_confidence(self) -> None:
        """Test graduated confidence calculation."""
        # Base 0.6, max 0.85, similarity 1.0 -> should be 0.85
        score = graduated_confidence(0.6, 1.0, 0.0, 0.85)
        assert score == 0.85

        # Base 0.6, max 0.85, similarity 0.0 -> should be 0.6
        score = graduated_confidence(0.6, 0.0, 0.0, 0.85)
        assert score == 0.6

        # Base 0.6, max 0.85, similarity 0.5 -> should be 0.725
        score = graduated_confidence(0.6, 0.5, 0.0, 0.85)
        assert score == 0.725

    def test_graduated_confidence_clamping(self) -> None:
        """Test clamping of confidence values."""
        # Should not exceed max
        score = graduated_confidence(0.8, 1.0, 0.0, 0.9)
        assert score == 0.9

        # Should not go below min
        score = graduated_confidence(0.5, 0.0, 0.5, 1.0)
        assert score == 0.5
