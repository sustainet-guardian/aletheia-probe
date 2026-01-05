# SPDX-License-Identifier: MIT
"""Tests for RetractionWatchSource data source."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

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
            "aletheia_probe.updater.sources.retraction_watch.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            mock_cache.get_source_last_updated.return_value = None
            mock_DataSourceManager.return_value = mock_cache

            assert source.should_update() is True

    def test_should_update_recent_update(self, source):
        """Test should_update with recent update (< 7 days)."""
        with patch(
            "aletheia_probe.updater.sources.retraction_watch.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            recent_date = datetime.now() - timedelta(days=3)
            mock_cache.get_source_last_updated.return_value = recent_date
            mock_DataSourceManager.return_value = mock_cache

            assert source.should_update() is False

    def test_should_update_old_update(self, source):
        """Test should_update with old update (>= 7 days)."""
        with patch(
            "aletheia_probe.updater.sources.retraction_watch.DataSourceManager"
        ) as mock_DataSourceManager:
            mock_cache = Mock()
            old_date = datetime.now() - timedelta(days=8)
            mock_cache.get_source_last_updated.return_value = old_date
            mock_DataSourceManager.return_value = mock_cache

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
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()

            with patch.object(source, "_clone_repository", return_value=repo_path):
                result = await source.fetch_data()
                assert result == []
