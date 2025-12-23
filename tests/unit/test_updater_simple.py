# SPDX-License-Identifier: MIT
"""Simple tests for updater module to increase coverage."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.updater.core import DataSource, DataUpdater
from aletheia_probe.updater.utils import (
    calculate_risk_level,
    clean_html_tags,
    clean_publisher_name,
    deduplicate_journals,
    extract_year_from_text,
    normalize_journal_name,
    parse_date_string,
)
from aletheia_probe.validation import extract_issn_from_text, validate_issn


class MockDataSource(DataSource):
    """Mock data source for testing."""

    def __init__(self, name: str, assessment_type: str = "predatory"):
        self._name = name
        self.assessment_type = assessment_type

    def get_name(self) -> str:
        return self._name

    def get_list_type(self) -> str:
        return self.assessment_type

    def get_assessment_type(self) -> str:
        return self.assessment_type

    def should_update(self) -> bool:
        return True

    async def fetch_data(self) -> list[dict]:
        """Mock fetch data implementation."""
        return [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test journal 1",
                "issn": "1234-5678",
            },
            {
                "journal_name": "Test Journal 2",
                "normalized_name": "test journal 2",
                "publisher": "Test Publisher",
            },
        ]


class TestDataUpdater:
    """Test cases for DataUpdater."""

    def test_add_source(self):
        """Test adding a data source."""
        updater = DataUpdater()
        source = MockDataSource("test_source")

        updater.add_source(source)

        assert len(updater.sources) == 1
        assert updater.sources[0] is source

    def test_get_source_by_name(self):
        """Test getting a source by name."""
        updater = DataUpdater()
        source = MockDataSource("test_source")
        updater.add_source(source)

        retrieved = updater.get_source_by_name("test_source")
        assert retrieved is source

        # Test non-existent source
        assert updater.get_source_by_name("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_source_success(self):
        """Test successful source update."""
        updater = DataUpdater()
        source = MockDataSource("test_source")

        with patch(
            "aletheia_probe.updater.core.DataSourceManager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.clear_source_data.return_value = 0
            mock_cache.log_update = Mock()
            mock_cache.add_journal_list_entry = Mock()
            mock_get_cache_manager.return_value = mock_cache

            result = await updater.update_source(source)

            assert result["status"] == "success"
            assert result["records_updated"] == 2  # Mock returns 2 records

    @pytest.mark.asyncio
    async def test_update_source_error(self):
        """Test source update with error."""

        class ErrorDataSource(MockDataSource):
            async def fetch_data(self):
                raise OSError("Fetch failed")

        updater = DataUpdater()
        source = ErrorDataSource("error_source")

        with patch(
            "aletheia_probe.updater.core.DataSourceManager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.log_update = Mock()
            mock_get_cache_manager.return_value = mock_cache

            result = await updater.update_source(source)

            assert result["status"] == "failed"
            assert "Fetch failed" in result["error"]

    @pytest.mark.asyncio
    async def test_update_all_sources(self):
        """Test updating all sources."""
        updater = DataUpdater()
        source1 = MockDataSource("source1")
        source2 = MockDataSource("source2")

        updater.add_source(source1)
        updater.add_source(source2)

        with (
            patch(
                "aletheia_probe.updater.core.DataSourceManager"
            ) as mock_get_cache_manager,
            patch.object(updater, "update_source") as mock_update,
        ):
            mock_cache = Mock()
            mock_cache.cleanup_expired_cache.return_value = 3
            mock_get_cache_manager.return_value = mock_cache
            mock_update.return_value = {"status": "success", "records_updated": 5}

            result = await updater.update_all()

            assert "source1" in result
            assert "source2" in result
            assert result["source1"]["status"] == "success"
            assert result["source2"]["status"] == "success"

    def test_add_custom_list(self):
        """Test adding a custom list."""
        updater = DataUpdater()

        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("journal_name\nTest Journal\nAnother Journal")
            temp_file = Path(f.name)

        try:
            updater.add_custom_list(temp_file, "predatory", "test_list")

            # Should have added a custom list source
            assert len(updater.sources) == 1
            source = updater.sources[0]
            assert source.get_name() == "test_list"

        finally:
            temp_file.unlink(missing_ok=True)

    def test_normalize_journal_name(self):
        """Test journal name normalization."""

        # Test basic normalization
        assert (
            normalize_journal_name("Journal of Computer Science")
            == "journal of computer science"
        )
        assert normalize_journal_name("NATURE") == "nature"

        # Test special character removal and parenthetical content removal
        assert normalize_journal_name("Journal (Special Issue)") == "journal"

        # Test whitespace normalization
        assert normalize_journal_name("  Multiple   Spaces  ") == "multiple spaces"

    def test_extract_issn_from_text(self):
        """Test ISSN extraction from text."""

        # Test various ISSN formats
        assert extract_issn_from_text("ISSN: 1234-5678") == "1234-5678"
        assert extract_issn_from_text("ISSN 1234-5678") == "1234-5678"
        assert extract_issn_from_text("(ISSN: 1234-5678)") == "1234-5678"

        # Test no ISSN found
        assert extract_issn_from_text("No ISSN here") is None

    def test_clean_publisher_name(self):
        """Test publisher name cleaning."""

        # Test basic cleaning
        assert clean_publisher_name("Elsevier Inc.") == "Elsevier"
        assert clean_publisher_name("Springer-Verlag GmbH") == "Springer-Verlag"

        # Test whitespace trimming
        assert (
            clean_publisher_name("  Nature Publishing Group  ")
            == "Nature Publishing Group"
        )

        # Test empty/None handling
        assert clean_publisher_name("") == ""
        assert clean_publisher_name(None) == ""

    @pytest.mark.asyncio
    async def test_data_source_base_methods(self):
        """Test base DataSource methods."""
        source = MockDataSource("test")

        assert source.get_name() == "test"
        assert source.get_assessment_type() == "predatory"

        # Test fetch_data
        data = await source.fetch_data()
        assert len(data) == 2
        assert data[0]["journal_name"] == "Test Journal 1"

    def test_calculate_risk_level(self):
        """Test risk level calculation."""

        # Test different retraction counts
        assert calculate_risk_level(0, None) == "none"
        assert calculate_risk_level(2, None) == "low"
        assert calculate_risk_level(8, None) == "moderate"
        assert calculate_risk_level(15, None) == "high"
        assert calculate_risk_level(25, None) == "critical"

        # Test with publication data
        assert calculate_risk_level(5, 1000) == "low"  # 0.5% rate
        assert calculate_risk_level(10, 500) == "high"  # 2% rate


class TestHelperFunctions:
    """Test helper functions in updater module."""

    def test_validate_issn(self):
        """Test ISSN validation."""

        # Valid ISSNs
        assert validate_issn("1234-5678") is True
        assert validate_issn("0028-0836") is True

        # Invalid ISSNs
        assert validate_issn("1234-567X") is False  # Wrong check digit
        assert validate_issn("invalid") is False
        assert validate_issn("") is False
        assert validate_issn(None) is False

    def test_parse_date_string(self):
        """Test date string parsing."""

        # Test various date formats
        result = parse_date_string("2023-12-01")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 1

        result = parse_date_string("December 1, 2023")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12

        # Test invalid dates
        assert parse_date_string("invalid") is None
        assert parse_date_string("") is None

    def test_extract_year_from_text(self):
        """Test year extraction from text."""

        assert extract_year_from_text("Published in 2023") == 2023
        assert extract_year_from_text("Copyright 2022") == 2022
        assert extract_year_from_text("No year here") is None

    def test_clean_html_tags(self):
        """Test HTML tag cleaning."""

        assert clean_html_tags("<b>Bold text</b>") == "Bold text"
        assert clean_html_tags("<p>Paragraph</p>") == "Paragraph"
        assert clean_html_tags("No tags here") == "No tags here"

    def test_deduplicate_journals(self):
        """Test journal deduplication."""

        journals = [
            {"journal_name": "Test Journal", "issn": "1234-5678"},
            {"journal_name": "Test Journal", "issn": "1234-5678"},  # Duplicate
            {"journal_name": "Another Journal", "issn": "2345-6789"},
        ]

        deduplicated = deduplicate_journals(journals)
        assert len(deduplicated) == 2
        journal_names = [j["journal_name"] for j in deduplicated]
        assert "Test Journal" in journal_names
        assert "Another Journal" in journal_names
