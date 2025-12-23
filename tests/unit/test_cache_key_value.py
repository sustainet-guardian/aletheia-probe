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
