# SPDX-License-Identifier: MIT
"""Unit tests for the CrossrefAnalyzerBackend."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aletheia_probe.backends.crossref_analyzer import CrossrefAnalyzerBackend
from aletheia_probe.constants import MIN_REFERENCE_COUNT
from aletheia_probe.models import BackendStatus, QueryInput


@pytest.fixture
def backend() -> CrossrefAnalyzerBackend:
    """Fixture for the CrossrefAnalyzerBackend."""
    return CrossrefAnalyzerBackend(email="test@example.com")


def test_crossref_analyzer_backend_get_name(backend: CrossrefAnalyzerBackend) -> None:
    """Test that the backend returns the correct name."""
    assert backend.get_name() == "crossref_analyzer"


def test_crossref_analyzer_backend_get_description(
    backend: CrossrefAnalyzerBackend,
) -> None:
    """Test that the backend returns the correct description."""
    assert (
        backend.get_description()
        == "Analyzes metadata quality and publisher information from Crossref to detect predatory journals"
    )


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
        patch.object(
            backend, "_get_journal_by_issn", new_callable=AsyncMock
        ) as mock_get,
        patch.object(backend, "_analyze_metadata_quality") as mock_analyze,
    ):
        mock_get.side_effect = [None, {"title": "Test Journal"}]
        mock_analyze.return_value = {
            "assessment": "legitimate",
            "confidence": 0.8,
            "metrics": {},
            "red_flags": [],
            "green_flags": [],
        }
        result = await backend.query(query_input)
        assert result.status == BackendStatus.FOUND
        assert mock_get.call_count == 2
        mock_get.assert_any_call("1234-5679")
        mock_get.assert_any_call("8765-4321")


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
        patch.object(
            backend, "_get_journal_by_issn", new_callable=AsyncMock
        ) as mock_get,
    ):
        mock_get.side_effect = Exception("API Error")
        result = await backend.query(query_input)
        assert result.status == BackendStatus.ERROR
        assert "API Error" in result.error_message


@pytest.mark.asyncio
async def test_get_journal_by_issn_api_error(backend: CrossrefAnalyzerBackend) -> None:
    """Test that _get_journal_by_issn handles API errors."""
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status = 500
        mock_get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(Exception, match="Crossref API returned status 500"):
            await backend._get_journal_by_issn("1234-5679")


@pytest.mark.asyncio
async def test_get_journal_by_issn_timeout(backend: CrossrefAnalyzerBackend) -> None:
    """Test that _get_journal_by_issn handles timeouts."""
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.side_effect = asyncio.TimeoutError
        with pytest.raises(Exception, match="Crossref API timeout"):
            await backend._get_journal_by_issn("1234-5679")


def test_calculate_metadata_metrics_invalid_dois(
    backend: CrossrefAnalyzerBackend,
) -> None:
    """Test _calculate_metadata_metrics with invalid dois_by_year data."""
    journal_data = {
        "breakdowns": {"dois-by-issued-year": [[2020, 10], ["2021", 20], "invalid"]}
    }
    metrics, _ = backend._calculate_metadata_metrics(journal_data)
    assert "2021" not in metrics["dois_by_year"]


def test_check_metadata_green_flags(backend: CrossrefAnalyzerBackend) -> None:
    """Test various green flag conditions."""
    metrics = {
        "total_dois": 5000,
        "overall_metadata_quality": 45,
        "publisher": "Test Publisher",
    }
    quality_scores = {
        "orcids": 45,
        "funders": 25,
        "licenses": 60,
        "references": 0,
    }
    green_flags = backend._check_metadata_green_flags(metrics, quality_scores)
    assert "Good ORCID adoption: 45% of articles include author ORCIDs" in green_flags
    assert (
        "Moderate funding transparency: 25% of articles include funding information"
        in green_flags
    )
    assert (
        "Good license documentation: 60% of articles have license information"
        in green_flags
    )
    assert (
        "Good overall metadata quality: 45.0% average across key fields" in green_flags
    )

    metrics["total_dois"] = 15000
    green_flags = backend._check_metadata_green_flags(metrics, quality_scores)
    assert "Large publication volume: 15,000 DOIs registered" in green_flags

    metrics["total_dois"] = 1500
    green_flags = backend._check_metadata_green_flags(metrics, quality_scores)
    assert "Substantial publication volume: 1,500 DOIs registered" in green_flags


def test_check_metadata_red_flags(backend: CrossrefAnalyzerBackend) -> None:
    """Test various red flag conditions."""
    metrics = {
        "total_dois": 600,
        "overall_metadata_quality": 20,
        "publisher": "Test Publisher",
        "dois_by_year": [[2020, 100], [2021, 150], [2022, 600]],
    }
    quality_scores = {"orcids": 5, "funders": 1, "licenses": 4}
    journal_data = {}
    red_flags = backend._check_metadata_red_flags(metrics, quality_scores, journal_data)
    assert "Low ORCID adoption: only 5% of articles include author ORCIDs" in red_flags
    assert (
        "Minimal funding transparency: only 1% of articles include funding information"
        in red_flags
    )
    assert (
        "Poor license documentation: only 4% of articles have license information"
        in red_flags
    )
    assert "Low overall metadata quality: 20.0% average across key fields" in red_flags
    assert "Recent publication explosion: 600 DOIs in 2022 vs 125 average" in red_flags


def test_determine_metadata_assessment(backend: CrossrefAnalyzerBackend) -> None:
    """Test various assessment and confidence conditions."""
    metrics = {"total_dois": 500}
    # Test green flags
    assessment, confidence = backend._determine_metadata_assessment(
        [], ["flag1", "flag2"], metrics
    )
    assert assessment == "legitimate"
    assert confidence > 0.6

    assessment, confidence = backend._determine_metadata_assessment(
        [], ["flag1"], metrics
    )
    assert assessment == "legitimate"
    assert confidence == pytest.approx(0.55)

    # test low volume
    metrics["total_dois"] = 40
    assessment, confidence = backend._determine_metadata_assessment(
        [], ["flag1"], metrics
    )
    assert assessment == "legitimate"
    assert confidence == pytest.approx(0.55 * 0.8)
