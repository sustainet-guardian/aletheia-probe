# SPDX-License-Identifier: MIT
"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.cache import CacheManager, reset_cache_manager, set_cache_manager
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


@pytest.fixture(scope="function", autouse=True)
def isolated_test_cache(tmp_path):
    """
    Automatically provide an isolated test cache for every test.

    This fixture:
    1. Creates a temporary database file for each test
    2. Sets it as the global cache manager
    3. Cleans up after the test completes

    This prevents tests from accessing the production cache.db file.
    """
    # Create a temporary database file
    cache_path = tmp_path / "test_cache.db"

    # Create a cache manager instance with the test database
    test_cache = CacheManager(db_path=cache_path)

    # Set it as the global cache manager
    set_cache_manager(test_cache)

    # Yield control to the test
    yield test_cache

    # Clean up after the test
    reset_cache_manager()
    # The tmp_path fixture automatically cleans up the temp directory


@pytest.fixture
def sample_query_input():
    """Sample QueryInput for testing."""
    return QueryInput(
        raw_input="Journal of Advanced Computer Science",
        normalized_name="Journal of Advanced Computer Science",
        identifiers={"issn": "1234-5678"},
        aliases=["Advanced Computer Science"],
    )


@pytest.fixture
def sample_backend_result():
    """Sample BackendResult for testing."""
    return BackendResult(
        backend_name="test_backend",
        status=BackendStatus.FOUND,
        confidence=0.9,
        assessment="legitimate",
        data={"test": "data"},
        sources=["test_source"],
        response_time=0.1,
    )


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir
