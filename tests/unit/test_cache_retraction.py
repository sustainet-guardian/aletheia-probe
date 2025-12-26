# SPDX-License-Identifier: MIT
"""Tests for the cache retraction module."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import RetractionCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = RetractionCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestCacheRetraction:
    """Test cases for Cache Retraction."""

    def test_get_article_retraction(self, temp_cache):
        """Test getting cached article retraction."""
        # Cache a retraction
        temp_cache.cache_article_retraction(
            doi="10.1234/test",
            is_retracted=True,
            source="test_source",
            retraction_type="full",
            retraction_date="2023-01-01",
            retraction_doi="10.1234/retraction",
            retraction_reason="Fraud",
        )

        # Retrieve it
        result = temp_cache.get_article_retraction(doi="10.1234/test")

        assert result is not None
        assert result["is_retracted"]  # SQLite stores booleans as integers
        assert result["retraction_type"] == "full"

    def test_get_article_retraction_nonexistent(self, temp_cache):
        """Test that non-existent DOI returns None."""
        result = temp_cache.get_article_retraction(doi="10.1234/nonexistent")
        assert result is None

    def test_cleanup_expired_article_retractions(self, temp_cache):
        """Test cleanup of expired article retraction entries."""
        # Insert expired entries directly
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                """
                INSERT INTO article_retractions
                (doi, is_retracted, source, checked_at, expires_at)
                VALUES
                (?, ?, ?, CURRENT_TIMESTAMP, datetime('now', '-1 day')),
                (?, ?, ?, CURRENT_TIMESTAMP, datetime('now', '-2 days'))
                """,
                (
                    "10.1234/expired1",
                    True,
                    "test_source",
                    "10.1234/expired2",
                    False,
                    "test_source",
                ),
            )
            conn.commit()

        # Add a non-expired entry using the regular method
        temp_cache.cache_article_retraction(
            doi="10.1234/valid",
            is_retracted=True,
            source="test_source",
            ttl_hours=24,
        )

        # Cleanup expired entries
        removed_count = temp_cache.cleanup_expired_article_retractions()

        # Verify count of removed entries
        assert removed_count == 2

        # Verify expired entries are gone
        assert temp_cache.get_article_retraction(doi="10.1234/expired1") is None
        assert temp_cache.get_article_retraction(doi="10.1234/expired2") is None

        # Verify non-expired entry still exists
        result = temp_cache.get_article_retraction(doi="10.1234/valid")
        assert result is not None
        assert result["is_retracted"]
