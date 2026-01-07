# SPDX-License-Identifier: MIT
"""Simple tests for updater module to increase coverage."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.updater.core import DataSource
from aletheia_probe.updater.sync_utils import update_source_data
from aletheia_probe.updater.utils import deduplicate_journals
from aletheia_probe.validation import validate_issn


class MockDataSource(DataSource):
    """Mock data source for testing."""

    def __init__(
        self, name: str, assessment_type: AssessmentType = AssessmentType.PREDATORY
    ):
        self._name = name
        self.assessment_type = assessment_type

    def get_name(self) -> str:
        return self._name

    def get_list_type(self) -> AssessmentType:
        return self.assessment_type

    def get_assessment_type(self) -> str:
        return self.assessment_type.value

    def should_update(self) -> bool:
        return True

    async def fetch_data(self) -> list[dict]:
        """Mock fetch data implementation."""
        return [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test journal 1",
                "issn": "1234-5679",
            },
            {
                "journal_name": "Test Journal 2",
                "normalized_name": "test journal 2",
                "publisher": "Test Publisher",
            },
        ]


class TestUpdateSourceData:
    """Test cases for update_source_data function."""

    @pytest.mark.asyncio
    async def test_update_source_success(self):
        """Test successful source update."""
        source = MockDataSource("test_source")

        # Create mock AsyncDBWriter
        mock_db_writer = AsyncMock()
        mock_db_writer.queue_write = AsyncMock()

        with patch(
            "aletheia_probe.updater.sync_utils.DataSourceManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.log_update = Mock()
            mock_manager.register_data_source = Mock()
            mock_manager_class.return_value = mock_manager

            result = await update_source_data(source, mock_db_writer)

            assert result["status"] == "success"
            assert result["records_updated"] == 2  # Mock returns 2 records
            # Verify queue_write was called
            mock_db_writer.queue_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_source_error(self):
        """Test source update with error."""

        class ErrorDataSource(MockDataSource):
            async def fetch_data(self):
                raise OSError("Fetch failed")

        source = ErrorDataSource("error_source")

        # Create mock AsyncDBWriter
        mock_db_writer = AsyncMock()
        mock_db_writer.queue_write = AsyncMock()

        with patch(
            "aletheia_probe.updater.sync_utils.DataSourceManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.log_update = Mock()
            mock_manager.register_data_source = Mock()
            mock_manager_class.return_value = mock_manager

            result = await update_source_data(source, mock_db_writer)

            assert result["status"] == "failed"
            assert result["error"] == "Fetch failed"

    @pytest.mark.asyncio
    async def test_update_source_no_data(self):
        """Test source update when no data is returned."""

        class EmptyDataSource(MockDataSource):
            async def fetch_data(self):
                return []

        source = EmptyDataSource("empty_source")

        # Create mock AsyncDBWriter
        mock_db_writer = AsyncMock()

        with patch(
            "aletheia_probe.updater.sync_utils.DataSourceManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.log_update = Mock()
            mock_manager.register_data_source = Mock()
            mock_manager_class.return_value = mock_manager

            result = await update_source_data(source, mock_db_writer)

            assert result["status"] == "failed"
            assert result["error"] == "No data received"

    @pytest.mark.asyncio
    async def test_update_source_skip_when_not_needed(self):
        """Test source update skips when should_update returns False."""

        class NoUpdateNeededSource(MockDataSource):
            def should_update(self):
                return False

        source = NoUpdateNeededSource("no_update_source")
        mock_db_writer = AsyncMock()

        result = await update_source_data(source, mock_db_writer, force=False)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_update_needed"

    @pytest.mark.asyncio
    async def test_update_source_skip_with_reason(self):
        """Test source update skips with specific reason when provided."""

        class NoUpdateReasonSource(MockDataSource):
            def should_update(self):
                self.skip_reason = "already_up_to_date"
                return False

        source = NoUpdateReasonSource("reason_source")
        mock_db_writer = AsyncMock()

        result = await update_source_data(source, mock_db_writer, force=False)

        assert result["status"] == "skipped"
        assert result["reason"] == "already_up_to_date"

    @pytest.mark.asyncio
    async def test_update_source_force_update(self):
        """Test source update with force=True ignores should_update."""

        class NoUpdateNeededSource(MockDataSource):
            def should_update(self):
                return False

        source = NoUpdateNeededSource("forced_update_source")
        mock_db_writer = AsyncMock()
        mock_db_writer.queue_write = AsyncMock()

        with patch(
            "aletheia_probe.updater.sync_utils.DataSourceManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.log_update = Mock()
            mock_manager.register_data_source = Mock()
            mock_manager_class.return_value = mock_manager

            result = await update_source_data(source, mock_db_writer, force=True)

            assert result["status"] == "success"


class TestUtilityFunctions:
    """Test utility functions."""

    def test_deduplicate_journals(self):
        """Test journal deduplication."""
        journals = [
            {"journal_name": "Test Journal", "issn": "1234-5678"},
            {"journal_name": "Test Journal", "issn": "1234-5678"},  # Duplicate
            {"journal_name": "Other Journal", "issn": "8765-4321"},
        ]

        result = deduplicate_journals(journals)
        assert len(result) == 2

    def test_validate_issn(self):
        """Test ISSN validation."""
        # Test with actual valid ISSNs (checksum must be correct)
        assert validate_issn("0378-5955") is True  # Valid ISSN
        assert validate_issn("invalid") is False
        assert validate_issn("") is False
        # Invalid checksum
        assert validate_issn("1234-5678") is False
