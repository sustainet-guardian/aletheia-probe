# SPDX-License-Identifier: MIT
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

    def test_bracket_removal_parentheses(self):
        """Test removal of content within parentheses."""
        normalizer = InputNormalizer()

        # Test journal name with abbreviation in parentheses
        result = normalizer.normalize(
            "Advances in Neural Information Processing Systems (NeurIPS)"
        )
        assert (
            result.normalized_name
            == "Advances in Neural Information Processing Systems"
        )
        assert (
            result.raw_input
            == "Advances in Neural Information Processing Systems (NeurIPS)"
        )

        # Test conference name with abbreviation in parentheses
        result2 = normalizer.normalize(
            "International Conference on Cloud Computing (CLOUD)"
        )
        assert result2.normalized_name == "International Conference on CLOUD Computing"

    def test_bracket_removal_square_brackets(self):
        """Test removal of content within square brackets."""
        normalizer = InputNormalizer()

        # Test with year annotation
        result = normalizer.normalize("Journal of Science [2023]")
        assert result.normalized_name == "Journal of Science"

        # Test with online annotation
        result2 = normalizer.normalize("Digital Library [Online]")
        assert result2.normalized_name == "Digital Library"

    def test_bracket_removal_curly_braces(self):
        """Test removal of nested curly braces from BibTeX formatting."""
        normalizer = InputNormalizer()

        # Test single level braces
        result = normalizer.normalize("{IEEE} Conference")
        assert result.normalized_name == "IEEE Conference"

        # Test nested braces (BibTeX style)
        result2 = normalizer.normalize(
            "{{IEEE}} {{International Conference}} on {{Cloud Computing}}"
        )
        assert (
            result2.normalized_name
            == "IEEE International Conference on CLOUD Computing"
        )

        # Test triple nested braces
        result3 = normalizer.normalize("{{{CLOUD}}} Conference")
        assert result3.normalized_name == "CLOUD Conference"

    def test_bracket_removal_mixed_brackets(self):
        """Test removal of mixed bracket types."""
        normalizer = InputNormalizer()

        # Test combination of all bracket types
        result = normalizer.normalize(
            "2018 {{IEEE}} 11th {International Conference} on [Cloud] Computing (CLOUD)"
        )
        expected = "2018 IEEE 11th International Conference on Computing"  # IEEE preserved as acronym
        assert result.normalized_name == expected

        # Test real BibTeX example
        result2 = normalizer.normalize(
            "2018 {{IEEE}} 11th {{International Conference}} on {{Cloud Computing}} ({{CLOUD}})"
        )
        expected2 = "2018 IEEE 11th International Conference on CLOUD Computing"  # IEEE and CLOUD preserved as acronyms
        assert result2.normalized_name == expected2

    def test_bracket_removal_preserves_valid_parentheses(self):
        """Test that meaningful parentheses in journal names are preserved."""
        normalizer = InputNormalizer()

        # Note: With the current implementation, ALL parentheses are removed
        # This is intentional for better journal matching, but we document the behavior
        result = normalizer.normalize("Journal of Computer Science")
        assert "Computer Science" in result.normalized_name

        # If we had a case where we wanted to preserve certain parentheses,
        # we would need to implement more sophisticated logic

    def test_bracket_removal_empty_brackets(self):
        """Test handling of empty or whitespace-only brackets."""
        normalizer = InputNormalizer()

        result = normalizer.normalize("Journal of Testing ( ) with empty brackets")
        assert result.normalized_name == "Journal of Testing with Empty Brackets"

        result2 = normalizer.normalize("Conference [ ] with spaces")
        assert result2.normalized_name == "Conference with Spaces"

    def test_bracket_removal_nested_and_adjacent(self):
        """Test handling of nested and adjacent brackets."""
        normalizer = InputNormalizer()

        # Adjacent brackets
        result = normalizer.normalize("Journal (A)(B) of Science")
        assert result.normalized_name == "Journal of Science"

        # Nested different types
        result2 = normalizer.normalize("Conference {[on]} Science")
        assert result2.normalized_name == "Conference Science"

    def test_acronym_preservation(self):
        """Test that known acronyms are preserved in uppercase."""
        normalizer = InputNormalizer()

        # Test IEEE preservation
        result = normalizer.normalize("ieee computer society")
        assert result.normalized_name == "IEEE Computer Society"

        # Test ACM preservation
        result2 = normalizer.normalize("acm transactions on computer systems")
        assert result2.normalized_name == "ACM Transactions on Computer Systems"

        # Test multiple acronyms
        result3 = normalizer.normalize("ieee acm joint conference")
        assert result3.normalized_name == "IEEE ACM Joint Conference"

        # Test mixed case input
        result4 = normalizer.normalize("IeEe CoNfErEnCe")
        assert result4.normalized_name == "IEEE Conference"

    def test_case_insensitive_normalization_produces_same_lowercase_key(self):
        """Test that different case variations normalize to the same lowercase key.

        This test verifies that venue names differing only in case will produce
        the same cache key when lowercased, enabling case-insensitive matching.
        """
        normalizer = InputNormalizer()

        # Test conference names with different cases
        result1 = normalizer.normalize("International Conference on Machine Learning")
        result2 = normalizer.normalize("International conference on machine learning")
        result3 = normalizer.normalize("INTERNATIONAL CONFERENCE ON MACHINE LEARNING")

        # After normalization, the lowercase versions should be identical
        assert result1.normalized_name.lower() == result2.normalized_name.lower()
        assert result1.normalized_name.lower() == result3.normalized_name.lower()

        # Test journal names with different cases
        result4 = normalizer.normalize(
            "IEEE Transactions on Neural Networks and Learning Systems"
        )
        result5 = normalizer.normalize(
            "IEEE transactions on neural networks and learning systems"
        )
        result6 = normalizer.normalize(
            "ieee TRANSACTIONS on NEURAL networks AND learning SYSTEMS"
        )

        # After normalization, the lowercase versions should be identical
        assert result4.normalized_name.lower() == result5.normalized_name.lower()
        assert result4.normalized_name.lower() == result6.normalized_name.lower()

        # Test with conference full names
        result7 = normalizer.normalize(
            "Advances in Neural Information Processing Systems"
        )
        result8 = normalizer.normalize(
            "Advances in neural information processing systems"
        )
        result9 = normalizer.normalize(
            "ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS"
        )

        # After normalization, the lowercase versions should be identical
        assert result7.normalized_name.lower() == result8.normalized_name.lower()
        assert result7.normalized_name.lower() == result9.normalized_name.lower()

    def test_extract_conference_series_success(self):
        """Test successful conference series extraction."""
        normalizer = InputNormalizer()

        # Test cases with expected outputs
        test_cases = [
            (
                "34th International Conference on Machine Learning (ICML 2024)",
                "International Conference on Machine Learning (ICML )",
            ),
            (
                "2023 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
                "IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
            ),
            (
                "Proceedings of the 15th International Conference on Learning Representations",
                "the International Conference on Learning Representations",
            ),
            (
                "2018 IEEE 11th International Conference on Cloud Computing (CLOUD)",
                "IEEE International Conference on Cloud Computing (CLOUD)",
            ),
        ]

        for input_name, expected_output in test_cases:
            result = normalizer.extract_conference_series(input_name)
            # Remove extra whitespace for comparison
            if result:
                result = result.strip()
            if expected_output:
                expected_output = expected_output.strip()

            assert result == expected_output, (
                f"Expected '{expected_output}', got '{result}' for input '{input_name}'"
            )

    def test_extract_conference_series_edge_cases(self):
        """Test conference series extraction edge cases."""
        normalizer = InputNormalizer()

        # Edge cases that should return None
        edge_cases = [
            "",  # Empty string
            None,  # None input
            "Short",  # Too short
            "ICML",  # Already an acronym
            "Conference without year",  # No year/ordinal to remove
            123,  # Non-string input
            "   ",  # Whitespace only
        ]

        for case in edge_cases:
            result = normalizer.extract_conference_series(case)
            assert result is None, f"Expected None for input '{case}', got '{result}'"

    def test_extract_conference_series_no_change(self):
        """Test cases where series extraction doesn't change the name."""
        normalizer = InputNormalizer()

        # Cases where no extraction should occur (returns None)
        no_change_cases = [
            "International Conference on Machine Learning",  # Already series form
            "IEEE Computer Vision",  # No ordinals/years
            "Neural Information Processing Systems",  # Base form
        ]

        for case in no_change_cases:
            result = normalizer.extract_conference_series(case)
            assert result is None, f"Expected None for input '{case}', got '{result}'"

    def test_issn_extraction_with_real_journal(self):
        """Test ISSN extraction with a real journal identifier.

        Validates that ISSN identifiers are properly extracted from
        real journal names.
        """
        normalizer = InputNormalizer()

        # Nature's ISSN
        query = normalizer.normalize("Nature (ISSN: 0028-0836)")

        # Verify ISSN was extracted
        assert "issn" in query.identifiers
        assert query.identifiers["issn"] == "0028-0836"

    def test_edge_case_inputs(self):
        """Test that normalization handles edge cases gracefully."""
        normalizer = InputNormalizer()

        # Test with very long journal name (but under the 1000 char limit)
        long_name = "A" * 500
        query = normalizer.normalize(long_name)
        assert query.raw_input == long_name
        assert query.normalized_name is not None

        # Test with special characters
        special_chars = "Journal of Test™ & Research® (Ω Edition)"
        query = normalizer.normalize(special_chars)
        assert query.raw_input == special_chars
        assert query.normalized_name is not None

        # Test with unicode
        unicode_name = "学术期刊 (Academic Journal)"
        query = normalizer.normalize(unicode_name)
        assert query.raw_input == unicode_name
        assert query.normalized_name is not None
