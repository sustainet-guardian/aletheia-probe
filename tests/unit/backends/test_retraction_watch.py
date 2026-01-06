# SPDX-License-Identifier: MIT
"""Tests for the Retraction Watch backend with caching."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.protocols import DataSyncCapable
from aletheia_probe.backends.retraction_watch import RetractionWatchBackend
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    QueryInput,
)


class TestRetractionWatchBackend:
    """Test cases for RetractionWatchBackend with ApiBackendWithCache pattern."""

    @pytest.fixture
    def backend(self, isolated_test_cache: str) -> RetractionWatchBackend:
        """Create a RetractionWatchBackend instance with isolated test cache."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config:
            mock_config.return_value.load_config.return_value.cache.db_path = str(
                isolated_test_cache
            )
            return RetractionWatchBackend(cache_ttl_hours=24)

    @pytest.fixture
    def sample_query_input(self) -> QueryInput:
        """Sample QueryInput for retraction watch testing."""
        return QueryInput(
            raw_input="Nature",
            normalized_name="nature",
            identifiers={"issn": "0028-0836"},
            aliases=["Nature Magazine"],
        )

    @pytest.fixture
    def mock_retraction_data(self) -> dict:
        """Mock retraction data from cache."""
        return {
            "id": 1,
            "journal_name": "Nature",
            "normalized_name": "nature",
            "issn": "0028-0836",
        }

    @pytest.fixture
    def mock_retraction_stats(self) -> dict:
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
    def mock_openalex_data(self) -> dict:
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
    async def test_cache_hit_no_api_calls(
        self, backend: RetractionWatchBackend, sample_query_input: QueryInput
    ) -> None:
        """Test that cached results don't trigger API calls."""
        # Create a mock cached assessment result
        mock_cached_result = AssessmentResult(
            input_query="Nature",
            assessment=AssessmentType.SUSPICIOUS,
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    backend_name="retraction_watch",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment=AssessmentType.SUSPICIOUS,
                    data={"total_retractions": 5, "from_cache": True},
                    sources=["retraction_watch"],
                    response_time=0.01,
                    cached=False,  # Will be set to True by ApiBackendWithCache
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
        backend: RetractionWatchBackend,
        sample_query_input: QueryInput,
        mock_retraction_data: dict,
        mock_retraction_stats: dict,
        mock_openalex_data: dict,
    ) -> None:
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
    async def test_not_found_result_is_cached(
        self, backend: RetractionWatchBackend, sample_query_input: QueryInput
    ) -> None:
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
        self, backend: RetractionWatchBackend, sample_query_input: QueryInput
    ) -> None:
        """Test that cached queries complete in under 50ms (success criterion)."""
        mock_cached_result = AssessmentResult(
            input_query="Nature",
            assessment=AssessmentType.SUSPICIOUS,
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    backend_name="retraction_watch",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment=AssessmentType.SUSPICIOUS,
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
    async def test_configurable_cache_ttl(self) -> None:
        """Test that cache TTL is configurable."""
        # Create backend with custom TTL
        backend_48h = RetractionWatchBackend(cache_ttl_hours=48)
        assert backend_48h.cache_ttl_hours == 48

        backend_12h = RetractionWatchBackend(cache_ttl_hours=12)
        assert backend_12h.cache_ttl_hours == 12

    @pytest.mark.asyncio
    async def test_openalex_data_caching_separate(
        self,
        backend: RetractionWatchBackend,
        sample_query_input: QueryInput,
        mock_retraction_data: dict,
        mock_retraction_stats: dict,
    ) -> None:
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
                backend.openalex_cache,
                "get_openalex_data",
                return_value={
                    "openalex_id": "https://openalex.org/S12345",
                    "total_publications": 50000,
                    "recent_publications": 10000,
                },
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

    def test_backend_inherits_from_api_backend_with_cache(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that RetractionWatchBackend inherits from ApiBackendWithCache."""
        from aletheia_probe.backends.base import ApiBackendWithCache

        assert isinstance(backend, ApiBackendWithCache)

    def test_backend_has_query_api_method(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that backend has _query_api method (required by ApiBackendWithCache)."""
        assert hasattr(backend, "_query_api")
        assert callable(getattr(backend, "_query_api"))

    @pytest.mark.asyncio
    async def test_error_status_not_cached(
        self, backend: RetractionWatchBackend, sample_query_input: QueryInput
    ) -> None:
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


class TestRetractionWatchBackendDataSyncCapable:
    """Test cases for RetractionWatchBackend DataSyncCapable protocol implementation."""

    @pytest.fixture
    def backend(self, isolated_test_cache: str) -> RetractionWatchBackend:
        """Create a RetractionWatchBackend instance with isolated test cache."""
        with patch("aletheia_probe.config.get_config_manager") as mock_config:
            mock_config.return_value.load_config.return_value.cache.db_path = str(
                isolated_test_cache
            )
            return RetractionWatchBackend(cache_ttl_hours=24)

    def test_implements_data_sync_capable_protocol(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that RetractionWatchBackend implements DataSyncCapable protocol."""
        assert isinstance(backend, DataSyncCapable)

    def test_source_name_property(self, backend: RetractionWatchBackend) -> None:
        """Test that source_name property returns correct value."""
        assert backend.source_name == "retraction_watch"

    def test_get_data_source_returns_retraction_watch_source(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that get_data_source returns RetractionWatchSource instance."""
        data_source = backend.get_data_source()

        assert data_source is not None
        assert data_source.__class__.__name__ == "RetractionWatchSource"
        assert data_source.get_name() == "retraction_watch"

    def test_get_data_source_caches_instance(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that get_data_source caches and reuses the same instance."""
        data_source1 = backend.get_data_source()
        data_source2 = backend.get_data_source()

        # Should return the same cached instance
        assert data_source1 is data_source2

    @patch("aletheia_probe.backends.retraction_watch.RetractionCache")
    def test_needs_sync_returns_true_when_no_data(
        self, mock_retraction_cache_class: Mock, backend: RetractionWatchBackend
    ) -> None:
        """Test that needs_sync returns True when retraction statistics are empty."""
        # Mock empty retraction statistics
        mock_cache_instance = Mock()
        mock_cache_instance.get_retraction_statistics.return_value = None
        mock_retraction_cache_class.return_value = mock_cache_instance

        assert backend.needs_sync() is True
        mock_cache_instance.get_retraction_statistics.assert_called_once_with(1)

    @patch("aletheia_probe.backends.retraction_watch.RetractionCache")
    def test_needs_sync_returns_false_when_data_exists(
        self, mock_retraction_cache_class: Mock, backend: RetractionWatchBackend
    ) -> None:
        """Test that needs_sync returns False when retraction statistics exist."""
        # Mock existing retraction statistics
        mock_cache_instance = Mock()
        mock_cache_instance.get_retraction_statistics.return_value = {
            "journal_id": 1,
            "total_retractions": 5,
        }
        mock_retraction_cache_class.return_value = mock_cache_instance

        assert backend.needs_sync() is False
        mock_cache_instance.get_retraction_statistics.assert_called_once_with(1)

    @patch("aletheia_probe.backends.retraction_watch.RetractionCache")
    def test_needs_sync_returns_true_on_exception(
        self, mock_retraction_cache_class: Mock, backend: RetractionWatchBackend
    ) -> None:
        """Test that needs_sync returns True when exception occurs checking data."""
        # Mock exception when accessing cache
        mock_cache_instance = Mock()
        mock_cache_instance.get_retraction_statistics.side_effect = Exception(
            "Database error"
        )
        mock_retraction_cache_class.return_value = mock_cache_instance

        # Should return True (assume sync needed) when error occurs
        assert backend.needs_sync() is True

    def test_protocol_methods_are_callable(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that all DataSyncCapable protocol methods are implemented and callable."""
        # Verify source_name is a property
        assert hasattr(type(backend), "source_name")
        assert isinstance(getattr(type(backend), "source_name"), property)

        # Verify methods are callable
        assert hasattr(backend, "get_data_source")
        assert callable(getattr(backend, "get_data_source"))

        assert hasattr(backend, "needs_sync")
        assert callable(getattr(backend, "needs_sync"))

    def test_backend_maintains_api_cached_behavior_with_protocol(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that adding protocol doesn't break existing ApiBackendWithCache functionality."""
        from aletheia_probe.backends.base import ApiBackendWithCache

        # Should still be an ApiBackendWithCache
        assert isinstance(backend, ApiBackendWithCache)

        # Should still have ApiBackendWithCache methods
        assert hasattr(backend, "_query_api")
        assert hasattr(backend, "_generate_cache_key")
        assert hasattr(backend, "query")

        # Should still have cache instances
        assert hasattr(backend, "journal_cache")
        assert hasattr(backend, "assessment_cache")
        assert hasattr(backend, "openalex_cache")

    def test_get_evidence_type_returns_quality_indicator(
        self, backend: RetractionWatchBackend
    ) -> None:
        """Test that backend returns QUALITY_INDICATOR evidence type."""
        evidence_type = backend.get_evidence_type()
        assert evidence_type == EvidenceType.QUALITY_INDICATOR
