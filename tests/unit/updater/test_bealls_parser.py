# SPDX-License-Identifier: MIT
"""Unit tests for the Beall's List HTML parser.

This module provides test coverage for the BeallsHTMLParser, ensuring correct
extraction of journal and publisher information from various HTML structures
used in Beall's List (both list and table formats). It also verifies the
robustness of the name extraction logic and integration with normalization
and validation components.
"""

from unittest.mock import Mock, patch

import pytest

from aletheia_probe.updater.sources.bealls_helpers.parser import BeallsHTMLParser


class TestBeallsHTMLParser:
    """Test suite for BeallsHTMLParser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return BeallsHTMLParser()

    def test_init(self, parser):
        """Test parser initialization."""
        assert parser.cleaner is not None
        assert parser.validator is not None

    def test_parse_beallslist_html_basic(self, parser):
        """Test parsing basic HTML list structure."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a> (ASJ)</li>
            <li><a href="http://example.com">Global Research Journal</a></li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        assert len(results) == 2
        assert results[0]["journal_name"] == "International Journal of Science"
        assert results[0]["publisher"] == "ASJ"
        assert results[0]["metadata"]["source_url"] == "http://test.com"
        assert results[1]["journal_name"] == "Global Research Journal"
        assert results[1]["publisher"] is None

    def test_parse_beallslist_html_with_nested_tags(self, parser):
        """Test parsing HTML with nested tags in link text."""
        html = """
        <ul>
            <li><a href="http://example.com"><strong>Advanced Journal of Research</strong></a> (XYZ)</li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["journal_name"] == "Advanced Journal of Research"
        assert results[0]["publisher"] == "XYZ"

    def test_parse_beallslist_html_skip_short_names(self, parser):
        """Test that very short publisher names are skipped."""
        html = """
        <ul>
            <li><a href="http://example.com">A</a></li>
            <li><a href="http://example.com">International Journal of Science</a></li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        # Only the second one should be included (first is too short)
        assert len(results) == 1
        assert results[0]["journal_name"] == "International Journal of Science"

    def test_parse_beallslist_html_entry_type_publisher(self, parser):
        """Test entry_type is 'publisher' for non-standalone URLs."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a></li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com/publishers")

        assert results[0]["metadata"]["entry_type"] == "publisher"

    def test_parse_beallslist_html_entry_type_journal(self, parser):
        """Test entry_type is 'journal' for standalone URLs."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a></li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com/standalone")

        assert results[0]["metadata"]["entry_type"] == "journal"

    def test_parse_beallslist_html_invalid_publisher(self, parser):
        """Test that invalid publishers are filtered out."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a></li>
            <li><a href="http://example.com">Invalid Entry</a></li>
        </ul>
        """

        # Mock validator to reject the second entry
        def mock_valid(name):
            return name == "International Journal of Science"

        with patch.object(
            parser.validator, "is_valid_publisher_entry", side_effect=mock_valid
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["journal_name"] == "International Journal of Science"

    def test_parse_beallslist_html_normalization_error(self, parser):
        """Test handling of normalization errors."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a></li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            with patch(
                "aletheia_probe.updater.sources.bealls_helpers.parser.input_normalizer.normalize",
                side_effect=Exception("Normalization failed"),
            ):
                results = parser.parse_beallslist_html(html, "http://test.com")

        # Should skip entries that fail normalization
        assert len(results) == 0

    def test_parse_table_content_basic(self, parser):
        """Test parsing basic HTML table structure."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science</td>
                <td>Publisher ABC</td>
            </tr>
            <tr>
                <td>Global Research Journal</td>
                <td>Publisher XYZ</td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        assert len(results) == 2
        assert results[0]["journal_name"] == "International Journal of Science"
        assert results[0]["publisher"] == "Publisher ABC"
        assert results[0]["metadata"]["table_data"] is True
        assert results[1]["journal_name"] == "Global Research Journal"
        assert results[1]["publisher"] == "Publisher XYZ"

    def test_parse_table_content_single_column(self, parser):
        """Test parsing table with single column (journal name only)."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science</td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["journal_name"] == "International Journal of Science"
        assert results[0]["publisher"] is None

    def test_parse_table_content_with_html_tags(self, parser):
        """Test parsing table cells with HTML tags."""
        html = """
        <table>
            <tr>
                <td><strong>International Journal of Science</strong></td>
                <td><em>Publisher ABC</em></td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["journal_name"] == "International Journal of Science"
        assert results[0]["publisher"] == "Publisher ABC"

    def test_parse_table_content_with_th_headers(self, parser):
        """Test parsing table with th header cells."""
        html = """
        <table>
            <tr>
                <th>Journal Name</th>
                <th>Publisher</th>
            </tr>
            <tr>
                <td>International Journal of Science</td>
                <td>Publisher ABC</td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        # Headers should be processed too (they will fail validation if not journal-like)
        # The actual journal entry should be present
        journal_results = [
            r
            for r in results
            if r["journal_name"] == "International Journal of Science"
        ]
        assert len(journal_results) == 1

    def test_parse_table_content_normalization_error(self, parser):
        """Test handling of normalization errors in table parsing."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science</td>
                <td>Publisher ABC</td>
            </tr>
        </table>
        """

        with patch(
            "aletheia_probe.updater.sources.bealls_helpers.parser.input_normalizer.normalize",
            side_effect=Exception("Normalization failed"),
        ):
            results = parser.parse_table_content(html, "http://test.com")

        # Should skip entries that fail normalization
        assert len(results) == 0

    def test_extract_journal_info_basic(self, parser):
        """Test extracting journal name from basic text."""
        journal_name, publisher = parser._extract_journal_info(
            "International Journal of Science"
        )

        assert journal_name == "International Journal of Science"
        assert publisher is None

    def test_extract_journal_info_with_parentheses_publisher(self, parser):
        """Test extracting journal and publisher with parentheses pattern."""
        journal_name, publisher = parser._extract_journal_info(
            "International Journal of Science (Publisher ABC)"
        )

        assert journal_name == "International Journal of Science"
        assert publisher == "Publisher ABC"

    def test_extract_journal_info_with_comma_publisher(self, parser):
        """Test extracting journal and publisher with comma pattern."""
        journal_name, publisher = parser._extract_journal_info(
            "International Journal of Science, Publisher ABC"
        )

        assert journal_name == "International Journal of Science"
        assert publisher == "Publisher ABC"

    def test_extract_journal_info_with_dash_publisher(self, parser):
        """Test extracting journal and publisher with dash pattern."""
        journal_name, publisher = parser._extract_journal_info(
            "International Journal of Science - Publisher ABC"
        )

        assert journal_name == "International Journal of Science"
        assert publisher == "Publisher ABC"

    def test_extract_journal_info_skip_long_publisher_comma(self, parser):
        """Test that very long publisher names after comma are treated as part of journal name."""
        long_text = "International Journal of Science, This is a very long publisher name that exceeds fifty characters limit"
        journal_name, publisher = parser._extract_journal_info(long_text)

        # Should treat entire text as journal name since publisher part is too long
        assert journal_name == long_text
        assert publisher is None

    def test_extract_journal_info_skip_long_publisher_dash(self, parser):
        """Test that very long publisher names after dash are treated as part of journal name."""
        long_text = "International Journal of Science - This is a very long publisher name that exceeds fifty characters limit"
        journal_name, publisher = parser._extract_journal_info(long_text)

        # Should treat entire text as journal name since publisher part is too long
        assert journal_name == long_text
        assert publisher is None

    def test_extract_journal_info_too_short(self, parser):
        """Test that very short text is rejected."""
        journal_name, publisher = parser._extract_journal_info("AB")

        assert journal_name is None
        assert publisher is None

    def test_extract_journal_info_empty(self, parser):
        """Test that empty text is rejected."""
        journal_name, publisher = parser._extract_journal_info("")

        assert journal_name is None
        assert publisher is None

    def test_extract_journal_info_whitespace_only(self, parser):
        """Test that whitespace-only text is rejected."""
        journal_name, publisher = parser._extract_journal_info("   ")

        assert journal_name is None
        assert publisher is None

    def test_extract_journal_info_invalid_journal(self, parser):
        """Test that invalid journal entries are rejected."""
        with patch.object(
            parser.validator, "is_valid_journal_entry", return_value=False
        ):
            journal_name, publisher = parser._extract_journal_info("Invalid Entry")

        assert journal_name is None
        assert publisher is None

    def test_extract_journal_info_with_cleaner(self, parser):
        """Test that text is cleaned before processing."""
        with patch.object(
            parser.cleaner, "clean_malformed_text", return_value="Cleaned Journal Name"
        ):
            with patch.object(
                parser.validator, "is_valid_journal_entry", return_value=True
            ):
                journal_name, publisher = parser._extract_journal_info("  Dirty Text  ")

        assert journal_name == "Cleaned Journal Name"
        assert publisher is None

    def test_extract_journal_info_parentheses_invalid_journal_name(self, parser):
        """Test parentheses pattern where journal name part is invalid."""
        with patch.object(parser.validator, "is_valid_journal_entry") as mock_valid:
            # First call is for the full text, second call is for the journal name part
            mock_valid.side_effect = [True, False]
            journal_name, publisher = parser._extract_journal_info(
                "Invalid (Publisher)"
            )

        # Should fall back to treating entire text as journal name
        assert journal_name == "Invalid (Publisher)"
        assert publisher is None

    def test_extract_journal_info_comma_invalid_journal_name(self, parser):
        """Test comma pattern where journal name part is invalid."""
        with patch.object(parser.validator, "is_valid_journal_entry") as mock_valid:
            # First call is for the full text, second call is for the journal name part
            mock_valid.side_effect = [True, False]
            journal_name, publisher = parser._extract_journal_info("Invalid, Publisher")

        # Should fall back to treating entire text as journal name
        assert journal_name == "Invalid, Publisher"
        assert publisher is None

    def test_extract_journal_info_dash_invalid_journal_name(self, parser):
        """Test dash pattern where journal name part is invalid."""
        with patch.object(parser.validator, "is_valid_journal_entry") as mock_valid:
            # First call is for the full text, second call is for the journal name part
            mock_valid.side_effect = [True, False]
            journal_name, publisher = parser._extract_journal_info(
                "Invalid - Publisher"
            )

        # Should fall back to treating entire text as journal name
        assert journal_name == "Invalid - Publisher"
        assert publisher is None

    def test_parse_table_content_extract_journal_info_integration(self, parser):
        """Test table parsing with _extract_journal_info integration."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science (Publisher ABC)</td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["journal_name"] == "International Journal of Science"
        assert results[0]["publisher"] == "Publisher ABC"

    def test_parse_table_content_extract_from_second_cell(self, parser):
        """Test that publisher from second cell is used when first cell extraction fails."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science</td>
                <td>Publisher from Cell</td>
            </tr>
        </table>
        """

        results = parser.parse_table_content(html, "http://test.com")

        assert len(results) == 1
        assert results[0]["publisher"] == "Publisher from Cell"

    def test_parse_beallslist_html_raw_entry_metadata(self, parser):
        """Test that raw entry is stored in metadata."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a> (ASJ)</li>
        </ul>
        """

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        assert "raw_entry" in results[0]["metadata"]
        assert "International Journal of Science" in results[0]["metadata"]["raw_entry"]
        assert "(ASJ)" in results[0]["metadata"]["raw_entry"]

    def test_parse_beallslist_html_normalized_name(self, parser):
        """Test that normalized_name is populated correctly."""
        html = """
        <ul>
            <li><a href="http://example.com">International Journal of Science</a></li>
        </ul>
        """

        mock_normalized = Mock()
        mock_normalized.normalized_name = "international journal science"

        with patch.object(
            parser.validator, "is_valid_publisher_entry", return_value=True
        ):
            with patch(
                "aletheia_probe.updater.sources.bealls_helpers.parser.input_normalizer.normalize",
                return_value=mock_normalized,
            ):
                results = parser.parse_beallslist_html(html, "http://test.com")

        assert results[0]["normalized_name"] == "international journal science"

    def test_parse_table_content_normalized_name(self, parser):
        """Test that normalized_name is populated correctly in table parsing."""
        html = """
        <table>
            <tr>
                <td>International Journal of Science</td>
            </tr>
        </table>
        """

        mock_normalized = Mock()
        mock_normalized.normalized_name = "international journal science"

        with patch(
            "aletheia_probe.updater.sources.bealls_helpers.parser.input_normalizer.normalize",
            return_value=mock_normalized,
        ):
            results = parser.parse_table_content(html, "http://test.com")

        assert results[0]["normalized_name"] == "international journal science"

    def test_parse_beallslist_html_very_short_publisher(self, parser):
        """Test that very short publisher names (2 chars) are filtered out."""
        html = """
        <ul>
            <li><a href="http://example.com">AB</a></li>
            <li><a href="http://example.com">Valid Publisher Name</a></li>
        </ul>
        """

        with patch.object(
            parser.validator,
            "is_valid_publisher_entry",
            wraps=parser.validator.is_valid_publisher_entry,
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        # Only the valid publisher should be included
        assert len(results) == 1
        assert results[0]["journal_name"] == "Valid Publisher Name"

    def test_parse_beallslist_html_very_long_publisher(self, parser):
        """Test that very long publisher names are filtered out."""
        long_name = "A" * 250  # Exceeds MAX_PUBLISHER_NAME_LENGTH
        html = f"""
        <ul>
            <li><a href="http://example.com">{long_name}</a></li>
            <li><a href="http://example.com">Valid Publisher Name</a></li>
        </ul>
        """

        with patch.object(
            parser.validator,
            "is_valid_publisher_entry",
            wraps=parser.validator.is_valid_publisher_entry,
        ):
            results = parser.parse_beallslist_html(html, "http://test.com")

        # Only the valid publisher should be included
        assert len(results) == 1
        assert results[0]["journal_name"] == "Valid Publisher Name"
