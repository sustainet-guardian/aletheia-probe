# SPDX-License-Identifier: MIT
"""Unit tests for the CrossrefAnalyzerBackend."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aletheia_probe.backends.crossref_analyzer import CrossrefAnalyzerBackend
from aletheia_probe.enums import AssessmentType
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
        # Case 1: Generic Exception (e.g. network error)
        mock_get.side_effect = Exception("API Error")
        result = await backend.query(query_input)
        assert result.status == BackendStatus.ERROR
        assert "API Error" in result.error_message

        # Case 2: HTTP 500 Error (triggers BackendError in _get_journal_by_issn)
        mock_get.side_effect = None
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        # Need to simulate context manager
        mock_get.return_value.__aenter__.return_value = mock_response

        result = await backend.query(query_input)
        assert result.status == BackendStatus.ERROR
        assert "Crossref API returned status 500" in result.error_message


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


# --- New Comprehensive Tests ---


def create_journal_data(
    total_dois: int = 1000,
    orcids: float = 0.0,
    funders: float = 0.0,
    licenses: float = 0.0,
    references: float = 0.0,
    dois_by_year: list[list[int]] | None = None,
    abstracts: float = 0.0,
    affiliations: float = 0.0,
) -> dict:
    """Helper to create journal data with specific metrics."""
    if dois_by_year is None:
        dois_by_year = [[2020, 100]]

    return {
        "title": ["Test Journal"],
        "publisher": "Test Publisher",
        "counts": {
            "total-dois": total_dois,
            "current-dois": total_dois,
            "backfile-dois": 0,
        },
        "coverage": {
            "orcids": orcids,
            "funders": funders,
            "licenses": licenses,
            "references": references,
            "abstracts": abstracts,
            "affiliations": affiliations,
        },
        "coverage-type": {"current": {}},  # Empty current means fallback to coverage
        "breakdowns": {"dois-by-issued-year": dois_by_year},
    }


def test_analyze_metadata_legitimate_journal(backend: CrossrefAnalyzerBackend) -> None:
    """Test analysis of a high-quality legitimate journal."""
    journal_data = create_journal_data(
        total_dois=5000,
        orcids=80.0,  # High (> 70)
        funders=60.0,  # Good (> 40)
        licenses=90.0,  # Excellent (> 80)
        references=70.0,  # Good (> 60)
        abstracts=90.0,
        affiliations=90.0,
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    assert analysis["assessment"] == AssessmentType.LEGITIMATE
    # Should have high confidence due to many green flags + volume boost
    assert analysis["confidence"] > 0.7
    assert len(analysis["red_flags"]) == 0
    assert len(analysis["green_flags"]) >= 3

    green_text = " ".join(analysis["green_flags"])
    assert "High ORCID adoption" in green_text
    assert "Good funding transparency" in green_text
    assert "Excellent license documentation" in green_text
    assert (
        "Major publisher volume" in green_text
        or "Large publication volume" in green_text
        or "Substantial publication volume" in green_text
    )


def test_analyze_metadata_predatory_journal(backend: CrossrefAnalyzerBackend) -> None:
    """Test analysis of a likely predatory journal (low quality, small size)."""
    # Small-to-medium size journal with very poor metadata
    journal_data = create_journal_data(
        total_dois=200,  # _DOI_SMALL <= 200 < _DOI_LARGE
        orcids=2.0,  # Very low
        funders=0.0,  # None
        licenses=0.0,  # None
        references=10.0,
        abstracts=5.0,
        affiliations=5.0,
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    assert analysis["assessment"] == AssessmentType.PREDATORY
    assert len(analysis["red_flags"]) >= 3
    assert len(analysis["green_flags"]) == 0

    red_text = " ".join(analysis["red_flags"])
    assert "Very low ORCID adoption" in red_text
    assert "Minimal funding transparency" in red_text
    assert "Poor license documentation" in red_text


def test_analyze_metadata_recent_explosion(backend: CrossrefAnalyzerBackend) -> None:
    """Test detection of recent publication explosion."""
    # Steady state then explosion
    # Avg of previous 2 years: (50 + 50) / 2 = 50
    # Explosion: 600 (> 50 * 3 and > 500)
    dois_by_year = [
        [2018, 50],
        [2019, 50],
        [2020, 50],
        [2021, 600],  # Explosion
    ]

    journal_data = create_journal_data(
        total_dois=750, orcids=20.0, dois_by_year=dois_by_year
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    red_text = " ".join(analysis["red_flags"])
    assert "Recent publication explosion" in red_text
    assert "600 DOIs" in red_text


def test_analyze_metadata_volume_adjustment(backend: CrossrefAnalyzerBackend) -> None:
    """Test that confidence is adjusted based on publication volume."""
    # 1. High volume boost
    high_vol_data = create_journal_data(total_dois=2000, orcids=80.0, funders=50.0)
    analysis_high = backend._analyze_metadata_quality(high_vol_data)

    # 2. Very small volume reduction
    low_vol_data = create_journal_data(total_dois=10, orcids=80.0, funders=50.0)
    analysis_low = backend._analyze_metadata_quality(low_vol_data)

    # Both have same quality scores, but different volumes
    # High volume should have higher confidence (boosted)
    # Low volume should have lower confidence (reduced)

    # We verify the logic by checking if they are different in the expected direction
    # Assuming base confidence is same before adjustment
    assert analysis_high["confidence"] > analysis_low["confidence"]


def test_analyze_metadata_mixed_indicators(backend: CrossrefAnalyzerBackend) -> None:
    """Test analysis with mixed good and bad indicators."""
    # Good ORCID (Green) but No Funding/Licenses (Red for small journal)
    journal_data = create_journal_data(
        total_dois=100,
        orcids=80.0,  # Green flag
        funders=0.0,  # Red flag (for small/med journal)
        licenses=0.0,  # Red flag (for small/med journal)
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    # Should identify flags correctly
    green_text = " ".join(analysis["green_flags"])
    red_text = " ".join(analysis["red_flags"])

    assert "High ORCID adoption" in green_text
    assert "Minimal funding transparency" in red_text
    assert "Poor license documentation" in red_text

    # With conflicting signals, confidence might be lower or assessment might be None/Ambiguous
    # The current logic prioritizes MAJOR threshold (2 flags).
    # Here we have 1 Green, 2 Reds.
    # Logic: if red_flags >= 2 -> PREDATORY

    assert analysis["assessment"] == AssessmentType.PREDATORY


def test_analyze_metadata_new_operation_poor_practices(
    backend: CrossrefAnalyzerBackend,
) -> None:
    """Test detection of new operation with poor practices."""
    # Very small journal (< 50 DOIs) and poor quality
    journal_data = create_journal_data(
        total_dois=10,
        orcids=0.0,
        funders=0.0,
        licenses=0.0,
        abstracts=0.0,
        affiliations=0.0,
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    red_text = " ".join(analysis["red_flags"])
    assert "New operation with poor practices" in red_text


def test_analyze_metadata_moderate_quality(backend: CrossrefAnalyzerBackend) -> None:
    """Test analysis of a journal with moderate quality (no strong flags)."""
    # Use scores that average to something moderate (between 25 and 40)
    # 35 * 5 / 5 = 35. This is > 25 (Low) and < 40 (Good).

    journal_data = create_journal_data(
        total_dois=500,
        orcids=35.0,
        funders=15.0,
        licenses=35.0,
        abstracts=35.0,
        affiliations=35.0,
    )

    analysis = backend._analyze_metadata_quality(journal_data)

    assert len(analysis["red_flags"]) == 0
    assert len(analysis["green_flags"]) == 0
    assert analysis["assessment"] is None
