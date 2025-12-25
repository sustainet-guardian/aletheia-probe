# SPDX-License-Identifier: MIT
"""Tests for the DataSourceManager cache module."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aletheia_probe.cache import DataSourceManager
from aletheia_probe.cache.schema import init_database
from aletheia_probe.enums import AssessmentType, UpdateStatus


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing DataSourceManager."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = DataSourceManager(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestDataSourceManager:
    """Test cases for DataSourceManager."""

    def test_get_source_last_updated(self, temp_cache):
        """Test getting source last updated timestamp."""
        source_name = "test_source"

        # Initially no update time
        last_updated = temp_cache.get_source_last_updated(source_name)
        assert last_updated is None

        # Register the source first (required for log_update in normalized schema)
        temp_cache.register_data_source(
            source_name, "Test Source", AssessmentType.MIXED.value
        )

        # Log an update and capture the time (truncate to seconds for SQLite TIMESTAMP precision)
        before_update = datetime.now().replace(microsecond=0)
        temp_cache.log_update(
            source_name, "manual", UpdateStatus.SUCCESS.value, records_added=5
        )
        after_update = datetime.now().replace(microsecond=0) + timedelta(seconds=1)

        # Should now have update time that is recent (within the update window)
        last_updated = temp_cache.get_source_last_updated(source_name)
        assert last_updated is not None
        assert before_update <= last_updated <= after_update

    def test_log_update(self, temp_cache):
        """Test logging data source updates."""
        import sqlite3

        # First register the data source
        temp_cache.register_data_source(
            "test_source", "Test Source", AssessmentType.PREDATORY.value
        )

        temp_cache.log_update(
            "test_source", "full", UpdateStatus.SUCCESS.value, records_added=100
        )

        # Verify log entry in the new source_updates table
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT su.*, ds.name FROM source_updates su
                JOIN data_sources ds ON su.source_id = ds.id
                WHERE ds.name = ? AND su.status = ?
                ORDER BY su.completed_at DESC LIMIT 1
            """,
                ("test_source", UpdateStatus.SUCCESS.value),
            )

            result = cursor.fetchone()
            assert result is not None
            assert result[-1] == "test_source"  # ds.name (last column)
            assert result[3] == UpdateStatus.SUCCESS.value  # status
            assert result[4] == 100  # records_added
