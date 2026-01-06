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
