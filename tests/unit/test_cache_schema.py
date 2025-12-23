# SPDX-License-Identifier: MIT
"""Tests for cache database schema initialization."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Initialize database schema
    init_database(db_path)

    yield db_path

    # Cleanup
    db_path.unlink(missing_ok=True)


class TestCacheSchema:
    """Test cases for cache database schema."""

    def test_init_cache(self, temp_db):
        """Test cache initialization creates proper tables."""
        # Check that tables exist
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()

            # Check assessment_cache table
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='assessment_cache'
            """
            )
            assert cursor.fetchone() is not None

            # Check normalized tables
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='journals'
            """
            )
            assert cursor.fetchone() is not None

            # Check data_sources table
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='data_sources'
            """
            )
            assert cursor.fetchone() is not None
