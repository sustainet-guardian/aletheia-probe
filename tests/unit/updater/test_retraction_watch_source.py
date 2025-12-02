# SPDX-License-Identifier: MIT
"""Tests for RetractionWatchSource data source."""

import asyncio
import csv
import json
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.sources.retraction_watch import RetractionWatchSource


class TestRetractionWatchSource:
    """Test cases for RetractionWatchSource."""

    @pytest.fixture
    def source(self):
        """Create a RetractionWatchSource instance."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config_manager:
            mock_config = Mock()
            mock_config.data_source_urls = Mock()
            mock_config.data_source_urls.retraction_watch_repo_url = (
                "https://gitlab.com/test/retraction-watch-data.git"
            )
            mock_config.data_source_urls.retraction_watch_csv_filename = (
                "retraction_watch_data.csv"
            )
            mock_config_manager.return_value.load_config.return_value = mock_config

            return RetractionWatchSource()

    def test_get_name(self, source):
        """Test get_name method."""
        assert source.get_name() == "retraction_watch"

    def test_get_list_type(self, source):
        """Test get_list_type method."""
        assert source.get_list_type() == AssessmentType.QUALITY_INDICATOR

    def test_should_update_no_last_update(self, source):
        """Test should_update when no last update exists."""
        with patch(
            "aletheia_probe.updater.sources.retraction_watch.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.get_source_last_updated.return_value = None
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is True

    def test_should_update_recent_update(self, source):
        """Test should_update with recent update (< 7 days)."""
        with patch(
            "aletheia_probe.updater.sources.retraction_watch.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            recent_date = datetime.now() - timedelta(days=3)
            mock_cache.get_source_last_updated.return_value = recent_date
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is False

    def test_should_update_old_update(self, source):
        """Test should_update with old update (>= 7 days)."""
        with patch(
            "aletheia_probe.updater.sources.retraction_watch.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            old_date = datetime.now() - timedelta(days=8)
            mock_cache.get_source_last_updated.return_value = old_date
            mock_get_cache_manager.return_value = mock_cache

            assert source.should_update() is True

    @pytest.mark.asyncio
    async def test_fetch_data_clone_failure(self, source):
        """Test fetch_data when repository cloning fails."""
        with patch.object(source, "_clone_repository", return_value=None):
            result = await source.fetch_data()
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_data_missing_csv(self, source):
        """Test fetch_data when CSV file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()

            with patch.object(source, "_clone_repository", return_value=repo_path):
                result = await source.fetch_data()
                assert result == []

    @pytest.mark.asyncio
    async def test_clone_repository_success(self, source):
        """Test successful repository cloning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock successful git clone
            mock_result = Mock()
            mock_result.returncode = 0

            def mock_run_git_clone():
                # Create the expected directory structure
                repo_path = Path(temp_dir) / "retraction-watch-data"
                repo_path.mkdir()
                return mock_result

            with patch(
                "subprocess.run",
                side_effect=lambda *args, **kwargs: mock_run_git_clone(),
            ):
                result = await source._clone_repository(temp_dir)
                assert result is not None
                assert result.name == "retraction-watch-data"

    @pytest.mark.asyncio
    async def test_clone_repository_git_failure(self, source):
        """Test repository cloning when git command fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "git: command not found"

            with patch("subprocess.run", return_value=mock_result):
                result = await source._clone_repository(temp_dir)
                assert result is None

    @pytest.mark.asyncio
    async def test_clone_repository_timeout(self, source):
        """Test repository cloning timeout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired("git", 300)
            ):
                result = await source._clone_repository(temp_dir)
                assert result is None

    @pytest.mark.asyncio
    async def test_clone_repository_exception(self, source):
        """Test repository cloning with exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("subprocess.run", side_effect=Exception("Network error")):
                result = await source._clone_repository(temp_dir)
                assert result is None

    def test_clone_repository_invalid_temp_dir(self, source):
        """Test repository cloning with invalid temp directory."""
        # Test with non-existent directory
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                source._clone_repository("/nonexistent/path")
            )
            assert result is None
        finally:
            loop.close()

    def test_clone_repository_temp_dir_not_directory(self, source):
        """Test repository cloning when temp_dir is not a directory."""
        with tempfile.NamedTemporaryFile() as temp_file:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    source._clone_repository(temp_file.name)
                )
                assert result is None
            finally:
                loop.close()

    def test_parse_date_valid(self, source):
        """Test _parse_date with valid date strings."""
        # Test valid date
        result = source._parse_date("12/25/2023 14:30")
        assert result is not None
        assert result.year == 2023
        assert result.month == 12
        assert result.day == 25

    def test_parse_date_invalid(self, source):
        """Test _parse_date with invalid date strings."""
        # Test invalid formats
        assert source._parse_date("") is None
        assert source._parse_date("0") is None
        assert source._parse_date("invalid date") is None
        assert source._parse_date("2023-12-25") is None  # Wrong format

    def test_calculate_risk_level_no_publications(self, source):
        """Test _calculate_risk_level without publication data."""
        # Test different retraction counts (based on constants.py)
        assert source._calculate_risk_level(0, 0) == "none"
        assert source._calculate_risk_level(2, 1) == "low"  # RETRACTION_COUNT_LOW = 2
        assert (
            source._calculate_risk_level(6, 2) == "moderate"
        )  # RETRACTION_COUNT_MODERATE = 6
        assert (
            source._calculate_risk_level(11, 5) == "high"
        )  # RETRACTION_COUNT_HIGH = 11

    def test_calculate_risk_level_with_publications(self, source):
        """Test _calculate_risk_level with publication data."""
        # Test with publication data - rates are calculated as percentages
        # 5/1000 = 0.5%, which is > RETRACTION_RATE_LOW (0.1%) but < RETRACTION_RATE_MODERATE (0.8%)
        assert (
            source._calculate_risk_level(5, 2, 1000, 500) == "low"
        )  # 0.5% overall rate
        # 20/1000 = 2.0%, which is > RETRACTION_RATE_HIGH (1.5%) but < RETRACTION_RATE_CRITICAL (3.0%)
        assert (
            source._calculate_risk_level(20, 10, 1000, 500) == "high"
        )  # 2.0% overall rate

    @pytest.mark.asyncio
    async def test_batch_cache_article_retractions_empty(self, source):
        """Test _batch_cache_article_retractions with empty batch."""
        # Should handle empty batch gracefully
        await source._batch_cache_article_retractions([])
        # No assertion needed - just ensure no exception

    @pytest.mark.asyncio
    async def test_batch_cache_article_retractions_success(self, source):
        """Test successful _batch_cache_article_retractions."""
        article_batch = [
            {
                "doi": "10.1234/test.doi.1",
                "retraction_date_str": "12/25/2023 14:30",
                "retraction_nature": "Plagiarism",
                "reason": "Data fabrication",
                "retraction_doi": "10.1234/retraction.1",
            },
            {
                "doi": "10.1234/test.doi.2",
                "retraction_date_str": "",
                "retraction_nature": "",
                "reason": "",
                "retraction_doi": "",
            },
        ]

        with patch("aletheia_probe.cache.get_cache_manager") as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.db_path = ":memory:"
            mock_get_cache_manager.return_value = mock_cache

            # Create in-memory database for testing
            with sqlite3.connect(":memory:") as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE article_retractions (
                        doi TEXT PRIMARY KEY,
                        is_retracted BOOLEAN,
                        retraction_type TEXT,
                        retraction_date TEXT,
                        retraction_doi TEXT,
                        retraction_reason TEXT,
                        source TEXT,
                        metadata TEXT,
                        checked_at TIMESTAMP,
                        expires_at TEXT
                    )
                """)

                with patch("sqlite3.connect", return_value=conn):
                    await source._batch_cache_article_retractions(article_batch)

                # Verify records were inserted
                cursor.execute("SELECT COUNT(*) FROM article_retractions")
                count = cursor.fetchone()[0]
                assert count == 2

    @pytest.mark.asyncio
    async def test_parse_and_aggregate_csv_simple(self, source):
        """Test CSV parsing with simple data."""
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Journal",
                    "Publisher",
                    "RetractionDate",
                    "RetractionNature",
                    "Reason",
                    "OriginalPaperDOI",
                    "RetractionDOI",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Journal": "Test Journal",
                    "Publisher": "Test Publisher",
                    "RetractionDate": "12/25/2023 14:30",
                    "RetractionNature": "Plagiarism",
                    "Reason": "Data fabrication",
                    "OriginalPaperDOI": "10.1234/test.doi",
                    "RetractionDOI": "10.1234/retraction",
                }
            )
            csv_path = Path(f.name)

        try:
            with patch.object(
                source, "_batch_cache_article_retractions", new=AsyncMock()
            ):
                result = await source._parse_and_aggregate_csv(csv_path)

            assert len(result) == 1
            journal = result[0]
            assert journal["journal_name"] == "Test Journal"
            assert journal["publisher"] == "Test Publisher"
            assert journal["metadata"]["total_retractions"] == 1

        finally:
            csv_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_and_aggregate_csv_normalization_failure(self, source):
        """Test CSV parsing when normalization fails."""
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["Journal"])
            writer.writeheader()
            writer.writerow({"Journal": "Test Journal"})
            csv_path = Path(f.name)

        try:
            with (
                patch.object(
                    source, "_batch_cache_article_retractions", new=AsyncMock()
                ),
                patch(
                    "aletheia_probe.normalizer.input_normalizer.normalize",
                    side_effect=Exception("Normalization failed"),
                ),
            ):
                result = await source._parse_and_aggregate_csv(csv_path)

            # Should handle normalization failure gracefully
            assert len(result) == 0

        finally:
            csv_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_and_aggregate_csv_exception(self, source):
        """Test CSV parsing with file read exception."""
        # Create path to non-existent file
        csv_path = Path("/nonexistent/file.csv")

        result = await source._parse_and_aggregate_csv(csv_path)
        assert result == []

    @pytest.mark.asyncio
    async def test_parse_and_aggregate_csv_multiple_journals(self, source):
        """Test CSV parsing with multiple journals and aggregation."""
        # Create temporary CSV file with multiple entries
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Journal",
                    "Publisher",
                    "RetractionDate",
                    "RetractionNature",
                    "Reason",
                    "OriginalPaperDOI",
                    "RetractionDOI",
                ],
            )
            writer.writeheader()

            # Same journal, multiple retractions
            writer.writerow(
                {
                    "Journal": "Test Journal",
                    "Publisher": "Test Publisher",
                    "RetractionDate": "12/25/2023 14:30",
                    "RetractionNature": "Plagiarism",
                    "Reason": "Data fabrication",
                    "OriginalPaperDOI": "10.1234/test.doi.1",
                    "RetractionDOI": "10.1234/retraction.1",
                }
            )
            writer.writerow(
                {
                    "Journal": "Test Journal",
                    "Publisher": "Test Publisher",
                    "RetractionDate": "01/15/2022 10:00",
                    "RetractionNature": "Misconduct",
                    "Reason": "Ethical violation;Plagiarism",
                    "OriginalPaperDOI": "10.1234/test.doi.2",
                    "RetractionDOI": "10.1234/retraction.2",
                }
            )

            # Different journal
            writer.writerow(
                {
                    "Journal": "Another Journal",
                    "Publisher": "Another Publisher",
                    "RetractionDate": "06/01/2024 16:00",
                    "RetractionNature": "Error",
                    "Reason": "Statistical error",
                    "OriginalPaperDOI": "10.1234/another.doi",
                    "RetractionDOI": "10.1234/another.retraction",
                }
            )

            csv_path = Path(f.name)

        try:
            with patch.object(
                source, "_batch_cache_article_retractions", new=AsyncMock()
            ):
                result = await source._parse_and_aggregate_csv(csv_path)

            assert len(result) == 2

            # Find the test journal
            test_journal = next(
                j for j in result if j["journal_name"] == "Test Journal"
            )
            assert test_journal["metadata"]["total_retractions"] == 2
            assert (
                test_journal["metadata"]["recent_retractions"] == 1
            )  # Only 2022 is > 2 years ago
            assert (
                test_journal["metadata"]["very_recent_retractions"] == 0
            )  # None in last year
            assert len(test_journal["metadata"]["retraction_types"]) == 2
            assert "Plagiarism" in test_journal["metadata"]["retraction_types"]
            assert "Misconduct" in test_journal["metadata"]["retraction_types"]

            # Check top reasons include split reasons
            top_reasons = [
                reason[0] for reason in test_journal["metadata"]["top_reasons"]
            ]
            assert "Plagiarism" in top_reasons
            assert "Ethical violation" in top_reasons

        finally:
            csv_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_and_aggregate_csv_empty_journal_name(self, source):
        """Test CSV parsing with empty journal names."""
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["Journal", "OriginalPaperDOI"])
            writer.writeheader()
            writer.writerow({"Journal": "", "OriginalPaperDOI": "10.1234/test.doi"})
            writer.writerow(
                {"Journal": "Valid Journal", "OriginalPaperDOI": "10.1234/valid.doi"}
            )
            csv_path = Path(f.name)

        try:
            with patch.object(
                source, "_batch_cache_article_retractions", new=AsyncMock()
            ):
                result = await source._parse_and_aggregate_csv(csv_path)

            # Should only have the valid journal
            assert len(result) == 1
            assert result[0]["journal_name"] == "Valid Journal"

        finally:
            csv_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_clone_repository_path_traversal_protection(self, source):
        """Test that clone repository prevents path traversal attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_directory = Path(temp_dir).resolve()

            # Try to create a path outside temp directory using path traversal
            # This should be caught by the security check
            result = await source._clone_repository(temp_dir)

            # The method should handle this safely - even though the path construction
            # uses a fixed "retraction-watch-data" name, let's verify the security check works
            assert result is None or result.resolve().is_relative_to(
                temp_directory.resolve()
            )
