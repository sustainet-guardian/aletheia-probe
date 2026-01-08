# SPDX-License-Identifier: MIT
"""Tests for confidence scoring utilities."""

from aletheia_probe.confidence_utils import (
    MatchQuality,
    calculate_base_confidence,
    calculate_name_similarity,
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
