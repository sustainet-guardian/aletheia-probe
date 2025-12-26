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
            metadata={"note": "Test retraction"},
        )

        # Retrieve it
        result = temp_cache.get_article_retraction(doi="10.1234/test")

        assert result is not None
        assert result["is_retracted"]  # SQLite stores booleans as integers
        assert result["retraction_type"] == "full"
        assert result["metadata"]["note"] == "Test retraction"

    def test_get_article_retraction_nonexistent(self, temp_cache):
        """Test that non-existent DOI returns None."""
        result = temp_cache.get_article_retraction(doi="10.1234/nonexistent")
        assert result is None

    def test_get_article_retraction_invalid_json_metadata(self, temp_cache):
        """Test handling of invalid JSON in metadata field."""
        # Manually insert invalid JSON
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                """
                INSERT INTO article_retractions
                (doi, is_retracted, source, metadata, checked_at, expires_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, datetime('now', '+30 days'))
                """,
                ("10.1234/test", True, "test_source", "invalid{json"),
            )
            conn.commit()

        result = temp_cache.get_article_retraction(doi="10.1234/test")

        # Should still return result but with metadata set to None
        assert result is not None
        assert result["is_retracted"]  # SQLite stores booleans as integers
        assert result["metadata"] is None

    def test_cache_article_retraction_with_metadata(self, temp_cache):
        """Test caching article retraction with metadata."""
        temp_cache.cache_article_retraction(
            doi="10.1234/test",
            is_retracted=True,
            source="test_source",
            metadata={"key1": "value1", "key2": 123},
        )

        result = temp_cache.get_article_retraction(doi="10.1234/test")

        assert result is not None
        assert result["metadata"]["key1"] == "value1"
        assert result["metadata"]["key2"] == 123
