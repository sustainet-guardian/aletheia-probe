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
        # Insert expired entries using the public API with negative TTL
        temp_cache.cache_article_retraction(
            doi="10.1234/expired1",
            is_retracted=True,
            source="test_source",
            ttl_hours=-24,  # Expired 1 day ago
        )
        temp_cache.cache_article_retraction(
            doi="10.1234/expired2",
            is_retracted=False,
            source="test_source",
            ttl_hours=-48,  # Expired 2 days ago
        )

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

    def test_datetime_format_consistency(self, temp_cache):
        """Test that expires_at format is consistent with SQLite CURRENT_TIMESTAMP."""
        # Cache an entry
        temp_cache.cache_article_retraction(
            doi="10.1234/format-test",
            is_retracted=False,
            source="test_source",
            ttl_hours=1,
        )

        # Query the database directly to check the stored format
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT expires_at
                FROM article_retractions
                WHERE doi = ?
                """,
                ("10.1234/format-test",),
            )
            row = cursor.fetchone()
            assert row is not None
            expires_at_str = row[0]

            # Verify format matches SQLite timestamp (YYYY-MM-DD HH:MM:SS)
            # Should not contain 'T' separator or microseconds
            assert "T" not in expires_at_str
            assert len(expires_at_str) == 19  # 'YYYY-MM-DD HH:MM:SS'

            # Verify string comparison with CURRENT_TIMESTAMP works correctly
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM article_retractions
                WHERE doi = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                ("10.1234/format-test",),
            )
            count = cursor.fetchone()[0]
            # Should find the entry since it expires in 1 hour (future)
            assert count == 1
