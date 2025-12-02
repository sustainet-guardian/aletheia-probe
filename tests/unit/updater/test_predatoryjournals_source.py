# SPDX-License-Identifier: MIT
"""Tests for PredatoryJournalsSource data source."""

import asyncio
import csv
import io
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientTimeout

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.predatoryjournals import PredatoryJournalsSource


class TestPredatoryJournalsSource:
    """Test cases for PredatoryJournalsSource."""

    @pytest.fixture
    def source(self):
        """Create a PredatoryJournalsSource instance."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
            mock_config = Mock()
            mock_config.data_source_urls = Mock()
            mock_config.data_source_urls.predatory_journals_fallback_url = (
                "https://www.predatoryjournals.org/the-list/journals"
            )
            mock_config.data_source_urls.predatory_publishers_fallback_url = (
                "https://www.predatoryjournals.org/the-list/publishers"
            )
            mock_config_manager.return_value.load_config.return_value = mock_config

            return PredatoryJournalsSource()

    def test_get_name(self, source):
        """Test get_name method."""
        assert source.get_name() == "predatoryjournals"

    def test_get_list_type(self, source):
        """Test get_list_type method."""
        assert source.get_list_type() == AssessmentType.PREDATORY

    def test_should_update_no_last_update(self, source):
        """Test should_update when no last update exists."""
        with patch(
            "aletheia_probe.updater.sources.predatoryjournals.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.get_source_last_updated.return_value = None
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is True

    def test_should_update_recent_update(self, source):
        """Test should_update with recent update (< 30 days)."""
        with patch(
            "aletheia_probe.updater.sources.predatoryjournals.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            recent_date = datetime.now() - timedelta(days=15)
            mock_cache.get_source_last_updated.return_value = recent_date
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is False

    def test_should_update_old_update(self, source):
        """Test should_update with old update (>= 30 days)."""
        with patch(
            "aletheia_probe.updater.sources.predatoryjournals.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            old_date = datetime.now() - timedelta(days=35)
            mock_cache.get_source_last_updated.return_value = old_date
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is True

    @pytest.mark.asyncio
    async def test_fetch_data_success(self, source):
        """Test successful fetch_data with both journals and publishers."""
        mock_journals = [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test journal 1",
                "issn": "1234-5678",
            }
        ]
        mock_publishers = [
            {"journal_name": "Test Publisher 1", "normalized_name": "test publisher 1"}
        ]

        with patch.object(source, "_fetch_google_sheet") as mock_fetch:
            mock_fetch.side_effect = [mock_journals, mock_publishers]

            with patch(
                "aletheia_probe.updater.sources.predatoryjournals.deduplicate_journals"
            ) as mock_dedupe:
                mock_dedupe.return_value = mock_journals + mock_publishers

                result = await source.fetch_data()

                assert len(result) == 2
                assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_data_journals_error(self, source):
        """Test fetch_data when journal fetch fails."""
        mock_publishers = [
            {"journal_name": "Test Publisher 1", "normalized_name": "test publisher 1"}
        ]

        with patch.object(source, "_fetch_google_sheet") as mock_fetch:
            # First call (journals) raises exception, second call (publishers) succeeds
            mock_fetch.side_effect = [Exception("Network error"), mock_publishers]

            with patch(
                "aletheia_probe.updater.sources.predatoryjournals.deduplicate_journals"
            ) as mock_dedupe:
                mock_dedupe.return_value = mock_publishers

                result = await source.fetch_data()

                assert len(result) == 1
                assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_data_both_sources_fail(self, source):
        """Test fetch_data when both journal and publisher fetches fail."""
        with patch.object(source, "_fetch_google_sheet") as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")

            with patch(
                "aletheia_probe.updater.sources.predatoryjournals.deduplicate_journals"
            ) as mock_dedupe:
                mock_dedupe.return_value = []

                result = await source.fetch_data()

                assert len(result) == 0
                assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_google_sheet_success(self, source):
        """Test successful _fetch_google_sheet."""
        mock_csv_data = "Journal Name,ISSN\nTest Journal,1234-5678\n"
        mock_session = Mock()

        with (
            patch.object(
                source,
                "_discover_sheet_url",
                return_value="https://example.com/sheet.csv",
            ),
            patch.object(source, "_parse_csv", return_value=[{"name": "test"}]),
        ):
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=mock_csv_data)

            # Properly mock async context manager - session.get() returns context manager
            mock_context_manager = Mock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            mock_context_manager.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = Mock(return_value=mock_context_manager)

            result = await source._fetch_google_sheet(
                mock_session, "journals", "https://example.com"
            )

            assert len(result) == 1
            assert result[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_fetch_google_sheet_no_url_discovered(self, source):
        """Test _fetch_google_sheet when no URL is discovered."""
        mock_session = Mock()

        with patch.object(source, "_discover_sheet_url", return_value=None):
            result = await source._fetch_google_sheet(
                mock_session, "journals", "https://example.com"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_google_sheet_http_error(self, source):
        """Test _fetch_google_sheet with HTTP error."""
        mock_session = Mock()

        with patch.object(
            source, "_discover_sheet_url", return_value="https://example.com/sheet.csv"
        ):
            # Mock HTTP 404 response
            mock_response = AsyncMock()
            mock_response.status = 404

            # Properly mock async context manager - session.get() returns context manager
            mock_context_manager = Mock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
            mock_context_manager.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = Mock(return_value=mock_context_manager)

            result = await source._fetch_google_sheet(
                mock_session, "journals", "https://example.com"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_google_sheet_timeout(self, source):
        """Test _fetch_google_sheet with timeout."""
        mock_session = Mock()

        with patch.object(
            source, "_discover_sheet_url", side_effect=asyncio.TimeoutError()
        ):
            result = await source._fetch_google_sheet(
                mock_session, "journals", "https://example.com"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_google_sheet_exception(self, source):
        """Test _fetch_google_sheet with general exception."""
        mock_session = Mock()

        with patch.object(
            source, "_discover_sheet_url", side_effect=Exception("Network error")
        ):
            result = await source._fetch_google_sheet(
                mock_session, "journals", "https://example.com"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_discover_sheet_url_success(self, source):
        """Test successful _discover_sheet_url."""
        mock_session = Mock()
        mock_html = """
        <html>
        <body>
        <iframe src="https://docs.google.com/spreadsheets/d/1ABCDEFGhijklmnop123456789/edit#gid=0"></iframe>
        </body>
        </html>
        """

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)

        # Properly mock async context manager - session.get() returns context manager
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = Mock(return_value=mock_context_manager)

        result = await source._discover_sheet_url(mock_session, "https://example.com")

        expected_url = "https://docs.google.com/spreadsheets/d/1ABCDEFGhijklmnop123456789/export?format=csv"
        assert result == expected_url

    @pytest.mark.asyncio
    async def test_discover_sheet_url_no_match(self, source):
        """Test _discover_sheet_url when no Google Sheet URL is found."""
        mock_session = Mock()
        mock_html = "<html><body>No sheets here</body></html>"

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)

        # Properly mock async context manager - session.get() returns context manager
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = Mock(return_value=mock_context_manager)

        result = await source._discover_sheet_url(mock_session, "https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_discover_sheet_url_http_error(self, source):
        """Test _discover_sheet_url with HTTP error."""
        mock_session = Mock()

        # Mock HTTP 404 response
        mock_response = AsyncMock()
        mock_response.status = 404

        # Properly mock async context manager - session.get() returns context manager
        mock_context_manager = Mock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = Mock(return_value=mock_context_manager)

        result = await source._discover_sheet_url(mock_session, "https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_discover_sheet_url_exception(self, source):
        """Test _discover_sheet_url with exception."""
        mock_session = Mock()

        with patch.object(mock_session, "get", side_effect=Exception("Network error")):
            result = await source._discover_sheet_url(
                mock_session, "https://example.com"
            )

            assert result is None

    def test_parse_csv_success(self, source):
        """Test successful CSV parsing."""
        csv_content = "Journal Name,ISSN,Publisher\nTest Journal,1234-5678,Test Publisher\nAnother Journal,2345-6789,Another Publisher\n"

        with patch.object(source, "_parse_row") as mock_parse_row:
            mock_parse_row.side_effect = [
                {"journal_name": "Test Journal", "issn": "1234-5678"},
                {"journal_name": "Another Journal", "issn": "2345-6789"},
            ]

            result = source._parse_csv(csv_content, "journals")

            assert len(result) == 2
            assert mock_parse_row.call_count == 2

    def test_parse_csv_empty_rows(self, source):
        """Test CSV parsing with empty rows."""
        csv_content = (
            "Journal Name,ISSN\nTest Journal,1234-5678\n,\nAnother Journal,2345-6789\n"
        )

        with patch.object(source, "_parse_row") as mock_parse_row:
            mock_parse_row.side_effect = [
                {"journal_name": "Test Journal"},
                {"journal_name": "Another Journal"},
            ]

            result = source._parse_csv(csv_content, "journals")

            assert len(result) == 2
            # Should skip the empty row
            assert mock_parse_row.call_count == 2

    def test_parse_csv_exception(self, source):
        """Test CSV parsing with exception."""
        invalid_csv = "This is not valid CSV content"

        result = source._parse_csv(invalid_csv, "journals")

        assert result == []

    def test_parse_row_journal_with_standard_columns(self, source):
        """Test _parse_row for journal with standard column names."""
        row = {
            "Journal Name": "Test Journal",
            "ISSN": "1234-5678",
            "eISSN": "2345-6789",
            "Publisher": "Test Publisher",
        }

        result = source._parse_row(row, "journals")

        assert result is not None
        assert result["journal_name"] == "Test Journal"
        assert result["issn"] == "1234-5678"
        assert result["eissn"] == "2345-6789"
        assert result["publisher"] == "Test Publisher"

    def test_parse_row_publisher_with_alternative_columns(self, source):
        """Test _parse_row for publisher with alternative column names."""
        row = {"Publisher Name": "Test Publisher", "issn": "1234-5678"}

        result = source._parse_row(row, "publishers")

        assert result is not None
        assert result["journal_name"] == "Test Publisher"
        assert result["issn"] == "1234-5678"
        assert "publisher" not in result  # Publishers don't have publisher field

    def test_parse_row_fallback_name_detection(self, source):
        """Test _parse_row with fallback name detection."""
        row = {
            "Column1": "123",  # Should be skipped (numeric)
            "Column2": "AB",  # Should be skipped (too short)
            "Column3": "journal",  # Should be skipped (common header)
            "Column4": "Valid Journal Name",  # Should be used
        }

        result = source._parse_row(row, "journals")

        assert result is not None
        assert result["journal_name"] == "Valid Journal Name"

    def test_parse_row_no_valid_name(self, source):
        """Test _parse_row when no valid name can be found."""
        row = {"Column1": "123", "Column2": "AB", "Column3": "name"}

        result = source._parse_row(row, "journals")

        assert result is None

    def test_parse_row_normalization_failure(self, source):
        """Test _parse_row when normalization fails."""
        row = {"Journal Name": "Test Journal"}

        with patch(
            "aletheia_probe.updater.sources.predatoryjournals.input_normalizer.normalize",
            side_effect=Exception("Normalization failed"),
        ):
            result = source._parse_row(row, "journals")

            assert result is None

    def test_parse_row_all_issn_variations(self, source):
        """Test _parse_row with various ISSN column names."""
        # Test Print ISSN
        row1 = {"Journal Name": "Test Journal", "Print ISSN": "1234-5678"}
        result1 = source._parse_row(row1, "journals")
        assert result1["issn"] == "1234-5678"

        # Test Online ISSN
        row2 = {"Journal Name": "Test Journal", "Online ISSN": "2345-6789"}
        result2 = source._parse_row(row2, "journals")
        assert result2["eissn"] == "2345-6789"

        # Test E-ISSN
        row3 = {"Journal Name": "Test Journal", "E-ISSN": "3456-7890"}
        result3 = source._parse_row(row3, "journals")
        assert result3["eissn"] == "3456-7890"

    def test_initialization_sets_timeout(self, source):
        """Test that initialization sets appropriate timeout."""
        assert isinstance(source.timeout, ClientTimeout)
        assert source.timeout.total == 60

    def test_sources_configuration(self, source):
        """Test that sources are properly configured."""
        assert "journals" in source.sources
        assert "publishers" in source.sources
        assert source.sources["journals"]["name"] == "Predatory Journals List 2025"
        assert source.sources["publishers"]["name"] == "Predatory Publishers List 2025"
        assert (
            source.sources["journals"]["fallback_url"]
            == "https://www.predatoryjournals.org/the-list/journals"
        )
        assert (
            source.sources["publishers"]["fallback_url"]
            == "https://www.predatoryjournals.org/the-list/publishers"
        )
