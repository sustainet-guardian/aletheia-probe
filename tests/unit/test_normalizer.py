"""Tests for input normalizer."""

import pytest

from aletheia_probe.normalizer import InputNormalizer


class TestInputNormalizer:
    """Tests for InputNormalizer class."""

    def setUp(self):
        self.normalizer = InputNormalizer()

    def test_basic_normalization(self):
        """Test basic journal name normalization."""
        normalizer = InputNormalizer()
        result = normalizer.normalize("Journal of Computer Science")

        assert result.raw_input == "Journal of Computer Science"
        assert result.normalized_name == "Journal of Computer Science"
        assert "Computer Science" in result.aliases

    def test_abbreviation_expansion(self):
        """Test abbreviation expansion."""
        normalizer = InputNormalizer()
        result = normalizer.normalize("J. Sci. Tech.")

        assert result.normalized_name is not None
        assert "Journal" in result.normalized_name
        assert "Science" in result.normalized_name
        assert "Technology" in result.normalized_name

    def test_issn_extraction(self):
        """Test ISSN extraction from input."""
        normalizer = InputNormalizer()
        result = normalizer.normalize("Journal of Testing (ISSN: 1234-5678)")

        assert result.identifiers.get("issn") == "1234-5678"
        assert result.normalized_name is not None
        assert "1234-5678" not in result.normalized_name

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        normalizer = InputNormalizer()
        result = normalizer.normalize("  Journal    of     Testing   ")

        assert result.normalized_name == "Journal of Testing"

    def test_empty_input_validation(self):
        """Test validation of empty input."""
        normalizer = InputNormalizer()

        with pytest.raises(ValueError, match="Input cannot be empty"):
            normalizer.normalize("")

        with pytest.raises(ValueError, match="Input cannot be empty"):
            normalizer.normalize("   ")

    def test_long_input_validation(self):
        """Test validation of overly long input."""
        normalizer = InputNormalizer()
        long_input = "x" * 1001

        with pytest.raises(ValueError, match="Input too long"):
            normalizer.normalize(long_input)

    def test_special_character_cleaning(self):
        """Test removal of special characters."""
        normalizer = InputNormalizer()
        result = normalizer.normalize("Journal@#$%of^&*()Testing")

        # Should keep some characters like parentheses, remove others
        assert result.normalized_name is not None
        assert "@#$%^*" not in result.normalized_name
        assert "Journal" in result.normalized_name
        assert (
            "testing" in result.normalized_name.lower()
        )  # Case normalization changes case

    def test_conference_name_normalization(self):
        """Test conference name normalization."""
        normalizer = InputNormalizer()
        result = normalizer.normalize(
            "2018 IEEE 11th International Conference on Cloud Computing (CLOUD)"
        )

        assert result.normalized_name is not None
        # Should have generated an alias without the year and ordinal
        aliases_lower = [a.lower() for a in result.aliases]
        # Check that at least one alias has removed year/ordinal patterns
        assert any(
            "2018" not in alias and "11th" not in alias for alias in result.aliases
        )

    def test_proceedings_prefix_removal(self):
        """Test that 'Proceedings of' prefix generates aliases."""
        normalizer = InputNormalizer()
        result = normalizer.normalize(
            "Proceedings of Semantic Web Information Management"
        )

        assert result.normalized_name is not None
        # Should have an alias without the "Proceedings of" prefix
        assert "Semantic Web Information Management" in result.aliases

    def test_conference_series_extraction(self):
        """Test extraction of conference series name."""
        normalizer = InputNormalizer()

        # Test with year in conference name
        result1 = normalizer.normalize(
            "2023 IEEE International Conference on Cloud Computing"
        )
        # Should have an alias with year removed
        assert any("2023" not in alias for alias in result1.aliases)

        # Test with ordinal in conference name
        result2 = normalizer.normalize(
            "15th International Conference on Utility and Cloud Computing"
        )
        # Should have an alias with ordinal removed
        assert any("15th" not in alias for alias in result2.aliases)

    def test_conference_with_both_year_and_ordinal(self):
        """Test conference name with both year and ordinal."""
        normalizer = InputNormalizer()
        result = normalizer.normalize(
            "2022 IEEE/ACM 15th International Conference on Utility and Cloud Computing (UCC)"
        )

        assert result.normalized_name is not None
        # Should generate aliases with year and ordinal removed
        clean_aliases = [
            a
            for a in result.aliases
            if "2022" not in a and "15th" not in a and a != result.normalized_name
        ]
        assert len(clean_aliases) > 0
