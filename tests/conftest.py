"""Pytest configuration and shared fixtures."""

from pathlib import Path

import pytest

from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


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
