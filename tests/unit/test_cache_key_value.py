# SPDX-License-Identifier: MIT
"""Tests for the cache key-value module."""

import sqlite3
import tempfile
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aletheia_probe.cache import KeyValueCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache() -> Generator[KeyValueCache, None, None]:
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = KeyValueCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestCacheKeyValue:
    """Test cases for CacheKeyValue."""

    def test_cache_and_get_value(self, temp_cache):
        """Test key-value cache functionality."""
        # Cache a value
        temp_cache.set_cached_value(key="test_key", value="test_value", ttl_hours=24)

        # Retrieve it
        result = temp_cache.get_cached_value(key="test_key")
        assert result == "test_value"

    def test_get_cached_value_nonexistent(self, temp_cache):
        """Test that non-existent key returns None."""
        result = temp_cache.get_cached_value(key="nonexistent_key")
        assert result is None

    def test_set_cached_value_empty_key_raises_error(self, temp_cache):
        """Test that empty key raises ValueError."""
        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            temp_cache.set_cached_value(key="", value="test_value")

    def test_set_cached_value_whitespace_key_raises_error(self, temp_cache):
        """Test that whitespace-only key raises ValueError."""
        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            temp_cache.set_cached_value(key="   ", value="test_value")

    def test_set_cached_value_too_long_key_raises_error(self, temp_cache):
        """Test that key exceeding max length raises ValueError."""
        long_key = "x" * 256
        with pytest.raises(ValueError, match="Cache key exceeds maximum length"):
            temp_cache.set_cached_value(key=long_key, value="test_value")

    def test_set_cached_value_negative_ttl_raises_error(self, temp_cache):
        """Test that negative TTL raises ValueError."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            temp_cache.set_cached_value(
                key="test_key", value="test_value", ttl_hours=-1
            )

    def test_set_cached_value_zero_ttl_raises_error(self, temp_cache):
        """Test that zero TTL raises ValueError."""
        with pytest.raises(ValueError, match="TTL must be positive"):
            temp_cache.set_cached_value(key="test_key", value="test_value", ttl_hours=0)

    def test_set_cached_value_excessive_ttl_raises_error(self, temp_cache):
        """Test that TTL exceeding max allowed raises ValueError."""
        with pytest.raises(ValueError, match="TTL exceeds maximum allowed"):
            temp_cache.set_cached_value(
                key="test_key", value="test_value", ttl_hours=8761
            )

    def test_get_cached_value_empty_key_raises_error(self, temp_cache):
        """Test that empty key raises ValueError on get."""
        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            temp_cache.get_cached_value(key="")

    def test_get_cached_value_whitespace_key_raises_error(self, temp_cache):
        """Test that whitespace-only key raises ValueError on get."""
        with pytest.raises(ValueError, match="Cache key cannot be empty"):
            temp_cache.get_cached_value(key="   ")

    def test_get_cached_value_too_long_key_raises_error(self, temp_cache):
        """Test that key exceeding max length raises ValueError on get."""
        long_key = "x" * 256
        with pytest.raises(ValueError, match="Cache key exceeds maximum length"):
            temp_cache.get_cached_value(key=long_key)

    def test_set_cached_value_max_valid_key_length(self, temp_cache):
        """Test that key at max valid length works correctly."""
        max_key = "x" * 255
        temp_cache.set_cached_value(key=max_key, value="test_value")
        result = temp_cache.get_cached_value(key=max_key)
        assert result == "test_value"

    def test_set_cached_value_max_valid_ttl(self, temp_cache):
        """Test that TTL at max allowed value works correctly."""
        temp_cache.set_cached_value(key="test_key", value="test_value", ttl_hours=8760)
        result = temp_cache.get_cached_value(key="test_key")
        assert result == "test_value"

    def test_cleanup_expired_entries(self, temp_cache):
        """Test cleanup of expired cache entries."""
        # Add a valid entry
        temp_cache.set_cached_value(key="valid_key", value="valid_value", ttl_hours=24)

        # Manually insert an expired entry (bypassing validation)
        expired_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                "INSERT INTO key_value_cache (key, value, expires_at) VALUES (?, ?, ?)",
                ("expired_key", "expired_value", expired_time),
            )
            conn.commit()

        # Verify both entries exist in database before cleanup
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM key_value_cache")
            assert cursor.fetchone()[0] == 2

        # Cleanup
        expired_count = temp_cache.cleanup_expired_entries()

        # Verify cleanup removed exactly one entry
        assert expired_count == 1

        # Verify valid entry still exists
        result = temp_cache.get_cached_value(key="valid_key")
        assert result == "valid_value"

        # Verify expired entry is gone
        result = temp_cache.get_cached_value(key="expired_key")
        assert result is None

    def test_cleanup_expired_entries_empty(self, temp_cache):
        """Test cleanup when no expired entries exist."""
        # Add only valid entries
        temp_cache.set_cached_value(key="key1", value="value1", ttl_hours=24)
        temp_cache.set_cached_value(key="key2", value="value2", ttl_hours=48)

        # Cleanup should remove nothing
        expired_count = temp_cache.cleanup_expired_entries()
        assert expired_count == 0

        # Verify all entries still exist
        assert temp_cache.get_cached_value(key="key1") == "value1"
        assert temp_cache.get_cached_value(key="key2") == "value2"

    def test_cleanup_expired_entries_all_expired(self, temp_cache):
        """Test cleanup when all entries are expired."""
        # Manually insert multiple expired entries
        expired_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                "INSERT INTO key_value_cache (key, value, expires_at) VALUES (?, ?, ?)",
                ("expired_key1", "expired_value1", expired_time),
            )
            conn.execute(
                "INSERT INTO key_value_cache (key, value, expires_at) VALUES (?, ?, ?)",
                ("expired_key2", "expired_value2", expired_time),
            )
            conn.commit()

        # Cleanup should remove all entries
        expired_count = temp_cache.cleanup_expired_entries()
        assert expired_count == 2

        # Verify all entries are gone
        assert temp_cache.get_cached_value(key="expired_key1") is None
        assert temp_cache.get_cached_value(key="expired_key2") is None

    def test_get_cached_value_ignores_expired_entries(self, temp_cache):
        """Test that get_cached_value automatically ignores expired entries."""
        # Manually insert an expired entry
        expired_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_cache.db_path) as conn:
            conn.execute(
                "INSERT INTO key_value_cache (key, value, expires_at) VALUES (?, ?, ?)",
                ("expired_key", "expired_value", expired_time),
            )
            conn.commit()

        # Verify the entry exists in database
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM key_value_cache WHERE key = ?",
                ("expired_key",),
            )
            assert cursor.fetchone()[0] == 1

        # get_cached_value should return None for expired entry
        result = temp_cache.get_cached_value(key="expired_key")
        assert result is None

    def test_set_cached_value_large_value(self, temp_cache):
        """Test storing and retrieving large values."""
        # Create a large value (1MB of text)
        large_value = "x" * (1024 * 1024)
        temp_cache.set_cached_value(key="large_key", value=large_value, ttl_hours=24)

        result = temp_cache.get_cached_value(key="large_key")
        assert result == large_value

    def test_set_cached_value_special_characters(self, temp_cache):
        """Test storing values with special characters."""
        special_value = "Line1\nLine2\tTab\r\nWindows line"
        temp_cache.set_cached_value(
            key="special_key", value=special_value, ttl_hours=24
        )

        result = temp_cache.get_cached_value(key="special_key")
        assert result == special_value

    def test_set_cached_value_unicode(self, temp_cache):
        """Test storing values with unicode characters."""
        unicode_key = "unicode_测试_🔑"
        unicode_value = "Hello 世界! 🌍 Emoji test: 🎉🎊"
        temp_cache.set_cached_value(key=unicode_key, value=unicode_value, ttl_hours=24)

        result = temp_cache.get_cached_value(key=unicode_key)
        assert result == unicode_value

    def test_set_cached_value_updates_existing_key(self, temp_cache):
        """Test that setting an existing key updates the value."""
        # Set initial value
        temp_cache.set_cached_value(
            key="update_key", value="initial_value", ttl_hours=24
        )
        assert temp_cache.get_cached_value(key="update_key") == "initial_value"

        # Update with new value
        temp_cache.set_cached_value(
            key="update_key", value="updated_value", ttl_hours=48
        )
        result = temp_cache.get_cached_value(key="update_key")
        assert result == "updated_value"

        # Verify only one entry exists in database
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM key_value_cache WHERE key = ?", ("update_key",)
            )
            assert cursor.fetchone()[0] == 1
