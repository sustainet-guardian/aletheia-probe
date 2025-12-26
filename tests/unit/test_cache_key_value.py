# SPDX-License-Identifier: MIT
"""Tests for the cache key-value module."""

import tempfile
from pathlib import Path

import pytest

from aletheia_probe.cache import KeyValueCache
from aletheia_probe.cache.schema import init_database


@pytest.fixture
def temp_cache():
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
