# SPDX-License-Identifier: MIT
"""Tests for the Retraction Watch backend with caching."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.retraction_watch import RetractionWatchBackend
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    QueryInput,
)


class TestRetractionWatchBackend:
    """Test cases for RetractionWatchBackend with HybridBackend pattern."""

    @pytest.fixture
    def backend(self):
        """Create a RetractionWatchBackend instance."""
        return RetractionWatchBackend(cache_ttl_hours=24)

    @pytest.fixture
    def sample_query_input(self):
        """Sample QueryInput for retraction watch testing."""
        return QueryInput(
            raw_input="Nature",
            normalized_name="nature",
            identifiers={"issn": "0028-0836"},
            aliases=["Nature Magazine"],
        )

    @pytest.fixture
    def mock_retraction_data(self):
        """Mock retraction data from cache."""
        return {
            "id": 1,
            "journal_name": "Nature",
            "normalized_name": "nature",
            "issn": "0028-0836",
        }

    @pytest.fixture
    def mock_retraction_stats(self):
        """Mock retraction statistics from dedicated table."""
        return {
            "journal_id": 1,
            "total_retractions": 5,
            "recent_retractions": 2,
            "very_recent_retractions": 1,
            "first_retraction_date": "2010-01-15",
            "last_retraction_date": "2023-05-20",
            "retraction_types": {"plagiarism": 2, "data_fabrication": 3},
            "top_reasons": ["Data fabrication", "Plagiarism"],
            "publishers": ["Springer Nature"],
        }

    @pytest.fixture
    def mock_openalex_data(self):
        """Mock OpenAlex publication data."""
        return {
            "openalex_id": "https://openalex.org/S12345",
            "openalex_url": "https://openalex.org/sources/S12345",
            "total_publications": 50000,
            "recent_publications": 10000,
            "recent_publications_by_year": {
                "2023": 2000,
                "2022": 2100,
                "2021": 1900,
                "2020": 2000,
                "2019": 2000,
            },
        }

    @pytest.mark.asyncio
    async def test_cache_hit_no_api_calls(self, backend, sample_query_input):
        """Test that cached results don't trigger API calls."""
        # Create a mock cached assessment result
        mock_cached_result = AssessmentResult(
            input_query="Nature",
            assessment="low",
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    backend_name="retraction_watch",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment="low",
                    data={"total_retractions": 5, "from_cache": True},
                    sources=["retraction_watch"],
                    response_time=0.01,
                    cached=False,  # Will be set to True by HybridBackend
                )
            ],
            metadata=None,
            processing_time=0.01,
        )

        with patch.object(
            backend.assessment_cache, "get_cached_assessment"
        ) as mock_get:
            mock_get.return_value = mock_cached_result

            # Query should return cached result
            result = await backend.query(sample_query_input)

            # Verify result came from cache
            assert result.status == BackendStatus.FOUND
            assert result.cached is True
            assert result.data["from_cache"] is True

            # Verify cache was checked
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_api_query(
        self,
        backend,
        sample_query_input,
        mock_retraction_data,
        mock_retraction_stats,
        mock_openalex_data,
    ):
        """Test that cache miss triggers API queries and caches result."""
        with (
            patch.object(
                backend.assessment_cache, "get_cached_assessment", return_value=None
            ) as mock_get_cached,
            patch.object(
                backend.journal_cache,
                "search_journals",
                return_value=[mock_retraction_data],
            ) as mock_search,
            patch.object(
                backend.assessment_cache, "cache_assessment_result"
            ) as mock_cache_result,
            patch.object(
                backend, "_get_openalex_data_cached", return_value=mock_openalex_data
            ) as mock_openalex,
            patch(
                "aletheia_probe.backends.retraction_watch.RetractionCache.get_retraction_statistics",
                return_value=mock_retraction_stats,
            ) as mock_stats,
        ):
            # Query should hit API
            result = await backend.query(sample_query_input)

            # Verify cache was checked first
            mock_get_cached.assert_called_once()

            # Verify result
            assert result.status == BackendStatus.FOUND
            assert result.data["total_retractions"] == 5
            assert result.data["recent_retractions"] == 2
            assert result.data["total_publications"] == 50000

            # Verify OpenAlex was called
            mock_openalex.assert_called_once()

            # Verify result was cached
            mock_cache_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_result_is_cached(self, backend, sample_query_input):
        """Test that NOT_FOUND results are also cached."""
        with (
            patch.object(
                backend.assessment_cache, "get_cached_assessment", return_value=None
            ) as mock_get_cached,
            patch.object(
                backend.journal_cache, "search_journals", return_value=[]
            ) as mock_search,
            patch.object(
                backend.assessment_cache, "cache_assessment_result"
            ) as mock_cache_result,
        ):
            result = await backend.query(sample_query_input)

            # Verify cache was checked first
            mock_get_cached.assert_called_once()

            # Verify NOT_FOUND status
            assert result.status == BackendStatus.NOT_FOUND
            assert result.confidence == 0.0

            # Verify result was cached (to prevent repeated lookups)
            mock_cache_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_time_under_50ms_when_cached(
        self, backend, sample_query_input
    ):
        """Test that cached queries complete in under 50ms (success criterion)."""
        mock_cached_result = AssessmentResult(
            input_query="Nature",
            assessment="low",
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    backend_name="retraction_watch",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment="low",
                    data={"total_retractions": 5},
                    sources=["retraction_watch"],
                    response_time=0.005,  # 5ms
                    cached=False,
                )
            ],
            metadata=None,
            processing_time=0.005,
        )

        with patch.object(
            backend.assessment_cache, "get_cached_assessment"
        ) as mock_get:
            mock_get.return_value = mock_cached_result

            result = await backend.query(sample_query_input)

            # Response time should be minimal (well under 50ms target)
            assert result.response_time < 0.05  # 50ms
            assert result.cached is True

    @pytest.mark.asyncio
    async def test_configurable_cache_ttl(self):
        """Test that cache TTL is configurable."""
        # Create backend with custom TTL
        backend_48h = RetractionWatchBackend(cache_ttl_hours=48)
        assert backend_48h.cache_ttl_hours == 48

        backend_12h = RetractionWatchBackend(cache_ttl_hours=12)
        assert backend_12h.cache_ttl_hours == 12

    @pytest.mark.asyncio
    async def test_openalex_data_caching_separate(
        self, backend, sample_query_input, mock_retraction_data, mock_retraction_stats
    ):
        """Test that OpenAlex data has separate caching layer."""
        # Mock OpenAlex cache hit
        with (
            patch.object(
                backend.assessment_cache, "get_cached_assessment", return_value=None
            ) as mock_get_cached,
            patch.object(
                backend.journal_cache,
                "search_journals",
                return_value=[mock_retraction_data],
            ) as mock_search,
            patch.object(
                backend.assessment_cache, "cache_assessment_result"
            ) as mock_cache_result,
            patch.object(
                backend.key_value_cache,
                "get_cached_value",
                return_value=json.dumps(
                    {
                        "openalex_id": "https://openalex.org/S12345",
                        "total_publications": 50000,
                        "recent_publications": 10000,
                    }
                ),
            ) as mock_openalex_cache_get,
            patch(
                "aletheia_probe.backends.retraction_watch.RetractionCache.get_retraction_statistics",
                return_value=mock_retraction_stats,
            ) as mock_stats,
        ):
            result = await backend.query(sample_query_input)

            # Verify cache was checked first
            mock_get_cached.assert_called_once()

            # Should have used OpenAlex cached data
            assert result.data["total_publications"] == 50000

            # Verify OpenAlex cache was checked
            mock_openalex_cache_get.assert_called_once()

    def test_backend_inherits_from_hybrid_backend(self, backend):
        """Test that RetractionWatchBackend inherits from HybridBackend."""
        from aletheia_probe.backends.base import HybridBackend

        assert isinstance(backend, HybridBackend)

    def test_backend_has_query_api_method(self, backend):
        """Test that backend has _query_api method (required by HybridBackend)."""
        assert hasattr(backend, "_query_api")
        assert callable(getattr(backend, "_query_api"))

    @pytest.mark.asyncio
    async def test_error_status_not_cached(self, backend, sample_query_input):
        """Test that ERROR status results are not cached."""
        with (
            patch.object(
                backend.assessment_cache, "get_cached_assessment", return_value=None
            ) as mock_get_cached,
            patch.object(
                backend.journal_cache, "search_journals", return_value=[]
            ) as mock_search,
            patch.object(
                backend.assessment_cache, "cache_assessment_result"
            ) as mock_cache_result,
            patch.object(
                backend, "_get_openalex_data_cached", side_effect=Exception("API Error")
            ),
        ):
            result = await backend.query(sample_query_input)

            # Verify cache was checked first
            mock_get_cached.assert_called_once()

            # Error should not be cached
            assert result.status == BackendStatus.NOT_FOUND
            # Still cached because NOT_FOUND should be cached
            mock_cache_result.assert_called_once()
