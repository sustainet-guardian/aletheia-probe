# SPDX-License-Identifier: MIT
"""Tests for AlgerianMinistrySource data source."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientTimeout

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.algerian import AlgerianMinistrySource


class TestAlgerianMinistrySource:
    """Test cases for AlgerianMinistrySource."""

    @pytest.fixture
    def source(self):
        """Create an AlgerianMinistrySource instance."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
            mock_config = Mock()
            mock_config.data_source_urls = Mock()
            mock_config.data_source_urls.algerian_ministry_base_url = (
                "https://dgrsdt.dz/storage/revus/"
            )
            mock_config_manager.return_value.load_config.return_value = mock_config

            return AlgerianMinistrySource()

    def test_get_name(self, source):
        """Test get_name method."""
        assert source.get_name() == "algerian_ministry"

    def test_get_list_type(self, source):
        """Test get_list_type method."""
        assert source.get_list_type() == AssessmentType.PREDATORY

    def test_initialization(self, source):
        """Test initialization sets up proper attributes."""
        assert isinstance(source.timeout, ClientTimeout)
        assert source.timeout.total == 300
        assert "Revues%20Pr%C3%A9datrices" in source.base_url
        assert source.current_year == datetime.now().year

    def test_should_update_no_last_update(self, source):
        """Test should_update when no last update exists."""
        with patch(
            "aletheia_probe.updater.sources.algerian.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            mock_cache.get_source_last_updated.return_value = None
            mock_DataSourceManager.return_value = mock_cache

            assert source.should_update() is True

    def test_should_update_recent_update(self, source):
        """Test should_update with recent update (< 30 days)."""
        with patch(
            "aletheia_probe.updater.sources.algerian.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            recent_date = datetime.now() - timedelta(days=15)
            mock_cache.get_source_last_updated.return_value = recent_date
            mock_DataSourceManager.return_value = mock_cache

            assert source.should_update() is False

    def test_should_update_old_update(self, source):
        """Test should_update with old update (>= 30 days)."""
        with patch(
            "aletheia_probe.updater.sources.algerian.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            old_date = datetime.now() - timedelta(days=35)
            mock_cache.get_source_last_updated.return_value = old_date
            mock_DataSourceManager.return_value = mock_cache

            assert source.should_update() is True

    @pytest.mark.asyncio
    async def test_fetch_data_success_2024(self, source):
        """Test successful fetch_data for 2024."""
        mock_journals = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test journal",
                "year": 2024,
            }
        ]

        with (
            patch.object(source, "_fetch_year_data", return_value=mock_journals),
            patch(
                "aletheia_probe.updater.sources.algerian.deduplicate_journals",
                return_value=mock_journals,
            ),
        ):
            result = await source.fetch_data()

            assert len(result) == 1
            assert result[0]["journal_name"] == "Test Journal"

    @pytest.mark.asyncio
    async def test_fetch_data_current_year_not_2024(self, source):
        """Test fetch_data when current year is not 2024."""
        source.current_year = 2025
        mock_journals = [{"journal_name": "Test Journal 2024"}]

        with (
            patch.object(source, "_fetch_year_data") as mock_fetch,
            patch(
                "aletheia_probe.updater.sources.algerian.deduplicate_journals",
                return_value=mock_journals,
            ),
        ):
            # First call (2024) succeeds, others shouldn't be called
            mock_fetch.return_value = mock_journals

            result = await source.fetch_data()

            # Should try 2024 first and succeed
            mock_fetch.assert_called_once_with(2024)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_data_year_failure_fallback(self, source):
        """Test fetch_data falls back to other years on failure."""
        source.current_year = 2025
        mock_journals = [{"journal_name": "Test Journal 2025"}]

        with (
            patch.object(source, "_fetch_year_data") as mock_fetch,
            patch(
                "aletheia_probe.updater.sources.algerian.deduplicate_journals",
                return_value=mock_journals,
            ),
        ):
            # First call (2024) fails, second (2025) succeeds
            mock_fetch.side_effect = [Exception("2024 failed"), mock_journals, []]

            result = await source.fetch_data()

            # Should try 2024, then 2025
            assert mock_fetch.call_count == 2
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_data_all_years_fail(self, source):
        """Test fetch_data when all years fail."""
        with (
            patch.object(source, "_fetch_year_data", side_effect=Exception("Failed")),
            patch(
                "aletheia_probe.updater.sources.algerian.deduplicate_journals",
                return_value=[],
            ),
        ):
            result = await source.fetch_data()

            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_year_data_success(self, source):
        """Test successful _fetch_year_data."""
        mock_journals = [{"journal_name": "Test Journal"}]

        with (
            patch.object(source, "_download_archive", return_value="/path/to/file.zip"),
            patch.object(source, "_extract_archive", return_value="/path/to/extracted"),
            patch.object(source, "_process_pdf_files", return_value=mock_journals),
        ):
            result = await source._fetch_year_data(2024)

            assert len(result) == 1
            assert result[0]["journal_name"] == "Test Journal"

    @pytest.mark.asyncio
    async def test_fetch_year_data_download_fails(self, source):
        """Test _fetch_year_data when download fails."""
        with patch.object(source, "_download_archive", return_value=None):
            result = await source._fetch_year_data(2024)

            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_year_data_extraction_fails(self, source):
        """Test _fetch_year_data when extraction fails."""
        with (
            patch.object(source, "_download_archive", return_value="/path/to/file.zip"),
            patch.object(source, "_extract_archive", return_value=None),
        ):
            result = await source._fetch_year_data(2024)

            assert result == []

    @pytest.mark.asyncio
    async def test_download_archive_success(self, source):
        """Test successful _download_archive."""
        mock_downloader = Mock()
        mock_downloader.download_archive = AsyncMock(return_value="/path/to/file.zip")
        source.downloader = mock_downloader

        result = await source._download_archive("https://example.com/file.zip", "/tmp")

        assert result == "/path/to/file.zip"
        mock_downloader.download_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_archive_zip_success(self, source):
        """Test successful _extract_archive."""
        mock_extractor = Mock()
        mock_extractor.extract_zip = AsyncMock(return_value="/path/to/extracted")
        source.extractor = mock_extractor

        result = await source._extract_archive("/path/to/file.zip", "/tmp")

        assert result == "/path/to/extracted"
        mock_extractor.extract_zip.assert_called_once_with("/path/to/file.zip", "/tmp")

    def test_process_pdf_files_nested_structure(self, source):
        """Test _process_pdf_files with nested directory structure."""
        mock_entries = [
            {"journal_name": "Journal 1", "type": "journal"},
            {"journal_name": "Publisher 1", "type": "publisher"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory structure: temp_dir/2024/2024/2024/
            year_dir = Path(temp_dir) / "2024" / "2024" / "2024"
            year_dir.mkdir(parents=True)

            # Create mock PDF files
            (year_dir / "Liste des revues predatrices 2024.pdf").touch()
            (year_dir / "Liste des éditeurs predateurs 2024.pdf").touch()

            mock_pdf_parser = Mock()
            mock_pdf_parser.parse_pdf_file.return_value = mock_entries[
                :1
            ]  # One entry per call
            source.pdf_parser = mock_pdf_parser

            result = source._process_pdf_files(temp_dir, 2024)

            # Should find nested structure and process both PDFs
            assert mock_pdf_parser.parse_pdf_file.call_count == 2
            assert len(result) == 2

    def test_process_pdf_files_simple_structure(self, source):
        """Test _process_pdf_files with simple directory structure."""
        mock_entries = [{"journal_name": "Journal 1", "type": "journal"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create simple directory structure: temp_dir/2024/
            year_dir = Path(temp_dir) / "2024"
            year_dir.mkdir(parents=True)

            # Create mock PDF files
            (year_dir / "Liste des revues predatrices 2024.pdf").touch()

            mock_pdf_parser = Mock()
            mock_pdf_parser.parse_pdf_file.return_value = mock_entries
            source.pdf_parser = mock_pdf_parser

            result = source._process_pdf_files(temp_dir, 2024)

            assert len(result) == 1
            assert result[0]["journal_name"] == "Journal 1"

    def test_process_pdf_files_no_year_directory(self, source):
        """Test _process_pdf_files when no year directory is found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Don't create any directories

            result = source._process_pdf_files(temp_dir, 2024)

            assert result == []

    def test_process_pdf_files_different_patterns(self, source):
        """Test _process_pdf_files recognizes different PDF file patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            year_dir = Path(temp_dir) / "2024"
            year_dir.mkdir(parents=True)

            # Create different pattern files
            (year_dir / "Liste des revues 2024.pdf").touch()
            (year_dir / "Actualisation liste 2024.pdf").touch()
            (year_dir / "Liste des éditeurs 2024.pdf").touch()

            mock_pdf_parser = Mock()
            mock_pdf_parser.parse_pdf_file.return_value = [{"name": "test"}]
            source.pdf_parser = mock_pdf_parser

            result = source._process_pdf_files(temp_dir, 2024)

            # Should process all three files
            assert mock_pdf_parser.parse_pdf_file.call_count == 3
            assert len(result) == 3

    def test_process_pdf_files_entry_type_detection(self, source):
        """Test _process_pdf_files correctly detects entry types."""
        with tempfile.TemporaryDirectory() as temp_dir:
            year_dir = Path(temp_dir) / "2024"
            year_dir.mkdir(parents=True)

            # Create files with different names
            journal_file = year_dir / "Liste des revues 2024.pdf"
            journal_file.touch()

            publisher_file = year_dir / "Liste des éditeurs 2024.pdf"
            publisher_file.touch()

            actualisation_file = year_dir / "Actualisation liste 2024.pdf"
            actualisation_file.touch()

            mock_pdf_parser = Mock()
            mock_pdf_parser.parse_pdf_file.return_value = [{"name": "test"}]
            source.pdf_parser = mock_pdf_parser

            result = source._process_pdf_files(temp_dir, 2024)

            # Check that correct entry types were passed
            calls = mock_pdf_parser.parse_pdf_file.call_args_list
            entry_types = [call[0][2] for call in calls]  # Third argument is entry_type

            assert "journal" in entry_types
            assert "publisher" in entry_types
            assert (
                len([t for t in entry_types if t == "journal"]) == 2
            )  # revues and actualisation

    def test_process_pdf_files_pdf_processing_error(self, source):
        """Test _process_pdf_files handles PDF processing errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            year_dir = Path(temp_dir) / "2024"
            year_dir.mkdir(parents=True)

            # Create PDF file
            (year_dir / "Liste des revues 2024.pdf").touch()

            mock_pdf_parser = Mock()
            mock_pdf_parser.parse_pdf_file.side_effect = Exception("PDF parsing error")
            source.pdf_parser = mock_pdf_parser

            result = source._process_pdf_files(temp_dir, 2024)

            # Should handle error and return empty list
            assert result == []

    def test_helper_classes_initialization(self, source):
        """Test that helper classes are properly initialized."""
        assert hasattr(source, "downloader")
        assert hasattr(source, "extractor")
        assert hasattr(source, "pdf_parser")

    @pytest.mark.asyncio
    async def test_fetch_data_with_current_year_2024(self, source):
        """Test fetch_data year order when current year is 2024."""
        source.current_year = 2024
        mock_journals = [{"journal_name": "Test Journal"}]

        with (
            patch.object(source, "_fetch_year_data") as mock_fetch,
            patch(
                "aletheia_probe.updater.sources.algerian.deduplicate_journals",
                return_value=mock_journals,
            ),
        ):
            mock_fetch.return_value = mock_journals

            result = await source.fetch_data()

            # Should try 2024 first when current year is 2024
            mock_fetch.assert_called_once_with(2024)
            assert len(result) == 1

    def test_base_url_construction(self, source):
        """Test that base URL is properly constructed from config."""
        assert source.base_url.startswith("https://dgrsdt.dz/storage/revus/")
        assert "Liste%20des%20Revues%20Pr%C3%A9datrices" in source.base_url
        assert "Editeurs%20pr%C3%A9dateurs" in source.base_url

    @pytest.mark.asyncio
    async def test_fetch_year_data_url_construction(self, source):
        """Test that _fetch_year_data constructs correct URLs."""
        with (
            patch.object(
                source, "_download_archive", return_value=None
            ) as mock_download,
            patch.object(source, "_extract_archive"),
            patch.object(source, "_process_pdf_files"),
        ):
            await source._fetch_year_data(2024)

            # Check that download_archive was called with correct URL
            expected_url = f"{source.base_url}/2024.zip"
            mock_download.assert_called_once()
            args, _ = mock_download.call_args
            assert args[0] == expected_url
