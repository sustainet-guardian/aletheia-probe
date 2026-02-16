# SPDX-License-Identifier: MIT
"""Unit tests for OpenCitations analyzer backend."""

from unittest.mock import AsyncMock, patch

import pytest

import aletheia_probe.backends  # noqa: F401 - ensure backend registration side effects
from aletheia_probe.backends.base import get_backend_registry
from aletheia_probe.backends.opencitations_analyzer import OpenCitationsAnalyzerBackend
from aletheia_probe.models import (
    BackendStatus,
    NormalizedVenueInput,
    QueryInput,
    VenueType,
)


@pytest.fixture
def backend() -> OpenCitationsAnalyzerBackend:
    """Fixture for OpenCitationsAnalyzerBackend."""
    return OpenCitationsAnalyzerBackend()


def test_opencitations_backend_get_name(backend: OpenCitationsAnalyzerBackend) -> None:
    """Test backend name."""
    assert backend.get_name() == "opencitations_analyzer"


def test_opencitations_backend_is_registered() -> None:
    """Test backend is registered in global backend registry."""
    registry_backend = get_backend_registry().get_backend("opencitations_analyzer")
    assert isinstance(registry_backend, OpenCitationsAnalyzerBackend)


def test_parse_count_payload_list(backend: OpenCitationsAnalyzerBackend) -> None:
    """Test parsing list-based count payload."""
    payload = [{"count": "12345"}]
    assert backend._parse_count_payload(payload) == 12345


@pytest.mark.asyncio
async def test_query_success_by_issn(backend: OpenCitationsAnalyzerBackend) -> None:
    """Test successful ISSN-based OpenCitations query."""
    query_input = QueryInput(
        raw_input="Nature",
        normalized_venue=NormalizedVenueInput(
            original_text="Nature",
            name="nature",
            acronym=None,
            issn="0028-0836",
            eissn=None,
            venue_type=VenueType.JOURNAL,
            aliases=[],
            input_identifiers={"issn": "0028-0836"},
        ),
    )

    metrics = {
        "issn": "0028-0836",
        "citation_count": 15000,
        "reference_count": 25000,
        "citation_count_url": "https://api.opencitations.net/index/v2/venue-citation-count/issn:0028-0836",
        "reference_count_url": "https://api.opencitations.net/index/v2/venue-reference-count/issn:0028-0836",
    }

    with (
        patch.object(
            backend.assessment_cache, "get_cached_assessment", return_value=None
        ),
        patch.object(backend, "_fetch_venue_metrics_by_issn", new=AsyncMock()) as mock,
    ):
        mock.return_value = metrics
        result = await backend.query(query_input)

    assert result.status == BackendStatus.FOUND
    assert result.assessment is not None
    assert result.data["opencitations_data"]["citation_count"] == 15000


@pytest.mark.asyncio
async def test_query_not_found_without_issn(
    backend: OpenCitationsAnalyzerBackend,
) -> None:
    """Test not-found result when no ISSN/eISSN is available."""
    query_input = QueryInput(
        raw_input="Unknown Venue",
        normalized_venue=NormalizedVenueInput(
            original_text="Unknown Venue",
            name="unknown venue",
            acronym=None,
            issn=None,
            eissn=None,
            venue_type=VenueType.JOURNAL,
            aliases=[],
            input_identifiers={},
        ),
    )

    with patch.object(
        backend.assessment_cache, "get_cached_assessment", return_value=None
    ):
        result = await backend.query(query_input)

    assert result.status == BackendStatus.NOT_FOUND
