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
        mock_response_200.json = AsyncMock(
            return_value={
                "message": {
                    "title": ["Test Journal"],
                    "publisher": "Test Publisher",
                    "counts": {"total-dois": 1000},
                    "coverage": {"orcids": 50, "funders": 30, "licenses": 70},
                    "coverage-type": {"current": {}},
                    "breakdowns": {
                        "dois-by-issued-year": [[2020, 100], [2021, 200], [2022, 300]]
                    },
                }
            }
        )

        # Mock the async context manager behavior for both calls
        mock_get.return_value.__aenter__.side_effect = [
            mock_response_404,
            mock_response_200,
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


def test_journal_size_classification_edge_cases(
    backend: CrossrefAnalyzerBackend,
) -> None:
    """Test journal size classification edge cases around 50-99 DOI range."""
    # Test very small journal (< 50 DOIs)
    assert backend._is_very_small_journal(25) is True
    assert backend._is_small_to_medium_journal(25) is False

    # Test journals in the previously uncovered 50-99 range
    assert backend._is_very_small_journal(50) is False
    assert backend._is_small_to_medium_journal(50) is True

    assert backend._is_very_small_journal(75) is False
    assert backend._is_small_to_medium_journal(75) is True

    assert backend._is_very_small_journal(99) is False
    assert backend._is_small_to_medium_journal(99) is True

    # Test boundary at 100 DOIs
    assert backend._is_very_small_journal(100) is False
    assert backend._is_small_to_medium_journal(100) is True

    # Test large journal (>= 10000 DOIs)
    assert backend._is_very_small_journal(15000) is False
    assert backend._is_small_to_medium_journal(15000) is False


def test_orcid_red_flag_applies_to_50_99_doi_journals(
    backend: CrossrefAnalyzerBackend,
) -> None:
    """Test that ORCID red flags now apply to journals with 50-99 DOIs."""
    # Create test data for a journal with 75 DOIs and low ORCID score
    journal_data = {
        "title": ["Test Journal"],
        "publisher": "Test Publisher",
        "counts": {"total-dois": 75, "current-dois": 75, "backfile-dois": 0},
        "coverage": {"orcids": 2.0, "funders": 1.0, "licenses": 3.0},  # Very low scores
        "coverage-type": {"current": {}},
        "breakdowns": {"dois-by-issued-year": [[2023, 75]]},
    }

    analysis = backend._analyze_metadata_quality(journal_data)

    # Should have red flags for low ORCID adoption since it's in small-to-medium range
    red_flag_texts = " ".join(analysis["red_flags"])
    assert "ORCID adoption" in red_flag_texts
    assert "funding transparency" in red_flag_texts
    assert "license documentation" in red_flag_texts
