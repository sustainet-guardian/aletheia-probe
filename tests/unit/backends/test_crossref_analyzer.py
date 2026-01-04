# SPDX-License-Identifier: MIT
"""Unit tests for the CrossrefAnalyzerBackend."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aletheia_probe.backends.crossref_analyzer import CrossrefAnalyzerBackend
from aletheia_probe.models import BackendStatus, QueryInput


@pytest.fixture
def backend() -> CrossrefAnalyzerBackend:
    """Fixture for the CrossrefAnalyzerBackend."""
    return CrossrefAnalyzerBackend(email="test@example.com")


def test_crossref_analyzer_backend_get_name(backend: CrossrefAnalyzerBackend) -> None:
    """Test that the backend returns the correct name."""
    assert backend.get_name() == "crossref_analyzer"


@pytest.mark.asyncio
async def test_query_api_with_eissn_fallback(backend: CrossrefAnalyzerBackend) -> None:
    """Test that the backend uses eissn if issn is not found."""
    query_input = QueryInput(
        raw_input="Test Journal",
        identifiers={"issn": "1234-5679", "eissn": "8765-4321"},
    )

    with (
        patch.object(
            backend.assessment_cache, "get_cached_assessment", return_value=None
        ),
        patch("aiohttp.ClientSession.get") as mock_get,
    ):
        # Setup mock responses: first ISSN returns 404, second eISSN returns data
        mock_response_404 = MagicMock()
        mock_response_404.status = 404

        mock_response_200 = MagicMock()
        mock_response_200.status = 200
        mock_response_200.json.return_value = {
            "message": {
                "title": ["Test Journal"],
                "publisher": "Test Publisher",
                "counts": {"total-dois": 1000},
                "coverage": {"orcids": 50, "funders": 30, "licenses": 70},
                "coverage-type": {"current": {}},
                "breakdowns": {"dois-by-issued-year": [[2020, 100], [2021, 200], [2022, 300]]},
            }
        }

        # First call (ISSN) returns 404, second call (eISSN) returns data
        mock_get.return_value.__aenter__.side_effect = [
            mock_response_404,
            mock_response_200
        ]

        result = await backend.query(query_input)
        assert result.status == BackendStatus.FOUND
        assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_query_api_exception_handling(backend: CrossrefAnalyzerBackend) -> None:
    """Test that the backend handles exceptions during API query."""
    query_input = QueryInput(
        raw_input="Test Journal", identifiers={"issn": "1234-5679"}
    )
    with (
        patch.object(
            backend.assessment_cache, "get_cached_assessment", return_value=None
        ),
        patch("aiohttp.ClientSession.get") as mock_get,
    ):
        mock_get.side_effect = Exception("API Error")
        result = await backend.query(query_input)
        assert result.status == BackendStatus.ERROR
        assert "API Error" in result.error_message