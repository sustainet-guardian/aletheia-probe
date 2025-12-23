# SPDX-License-Identifier: MIT
"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest

import aletheia_probe.backends  # Import backends to register them
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


@pytest.fixture(scope="function", autouse=True)
def isolated_test_cache(tmp_path):
    """
    Automatically provide an isolated test database path for every test.

    This fixture:
    1. Creates a temporary database file path for each test
    2. Initializes the database schema
    3. Returns the path for cache classes to use

    This prevents tests from accessing the production cache.db file.
    """
    # Local import to avoid circular dependency
    from aletheia_probe.cache.schema import init_database

    # Create a temporary database file
    cache_path = tmp_path / "test_cache.db"

    # Initialize the database schema
    init_database(cache_path)

    # Yield the path for tests to use
    yield cache_path

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
