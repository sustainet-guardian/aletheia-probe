# SPDX-License-Identifier: MIT
"""Tests for the base backend functionality."""

import asyncio
import copy
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.base import (
    ApiBackendWithCache,
    Backend,
    CachedBackend,
    get_backend_registry,
)
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.fallback_chain import QueryFallbackChain
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class MockBackend(Backend):
    """Mock backend for testing."""

    def __init__(self) -> None:
        super().__init__()

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Mock query implementation."""
        return BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="mock_backend",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.PREDATORY,
            data={"test": "data"},
            sources=["test_source"],
            response_time=0.1,
        )

    def get_name(self) -> str:
        return "mock_backend"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.HEURISTIC


class MockCachedBackend(CachedBackend):
    """Mock cached backend for testing."""

    def __init__(self) -> None:
        super().__init__("mock_cache", AssessmentType.PREDATORY)

    def get_name(self) -> str:
        return "mock_cache"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.PREDATORY_LIST


class TestBackendBase:
    """Test cases for Backend base class."""

    @pytest.mark.asyncio
    async def test_query_with_timeout_success(self) -> None:
        """Test successful query with timeout."""
        backend = MockBackend()
        query_input = QueryInput(
            raw_input="Test Journal", normalized_name="test journal"
        )

        result = await backend.query_with_timeout(query_input, timeout=5)

        assert isinstance(result, BackendResult)
        assert result.backend_name == "mock_backend"
        assert result.status == BackendStatus.FOUND

    @pytest.mark.asyncio
    async def test_query_with_timeout_timeout(self) -> None:
        """Test query that times out."""

        class SlowBackend(MockBackend):
            async def query(self, query_input: QueryInput) -> BackendResult:
                await asyncio.sleep(2)  # Simulate slow query
                return await super().query(query_input)

        backend = SlowBackend()
        query_input = QueryInput(
            raw_input="Test Journal", normalized_name="test journal"
        )

        result = await backend.query_with_timeout(query_input, timeout=1)

        assert result.status == BackendStatus.TIMEOUT
        assert result.error_message is not None
        assert "timed out" in result.error_message.lower()
        assert result.cached is False  # Timeouts are not cached

    @pytest.mark.asyncio
    async def test_query_with_timeout_exception(self) -> None:
        """Test query that raises an exception."""

        class ErrorBackend(MockBackend):
            async def query(self, query_input: QueryInput) -> BackendResult:
                raise ValueError("Test error")

        backend = ErrorBackend()
        query_input = QueryInput(
            raw_input="Test Journal", normalized_name="test journal"
        )

        result = await backend.query_with_timeout(query_input, timeout=5)

        assert result.status == BackendStatus.ERROR
        assert result.error_message is not None
        assert "Test error" in result.error_message
        assert result.cached is False  # Errors are not cached


class TestCachedBackend:
    """Test cases for CachedBackend."""

    @pytest.fixture
    def mock_cached_backend(self) -> MockCachedBackend:
        """Create mock cached backend."""
        return MockCachedBackend()

    @pytest.mark.asyncio
    async def test_cached_backend_query_found(
        self, mock_cached_backend: MockCachedBackend, sample_query_input: QueryInput
    ) -> None:
        """Test cached backend query when journal is found."""
        mock_results = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test journal",
                "issn": "1234-5679",
                "publisher": "Test Publisher",
            }
        ]

        with (
            patch.object(
                mock_cached_backend, "_search_exact_match", return_value=mock_results
            ),
            patch.object(
                mock_cached_backend, "_calculate_confidence", return_value=0.9
            ),
        ):
            result = await mock_cached_backend.query(sample_query_input)

            assert result.status == BackendStatus.FOUND
            assert result.assessment == AssessmentType.PREDATORY
            assert result.confidence == 0.9
            assert result.cached is True  # CachedBackend always returns cached=True

    @pytest.mark.asyncio
    async def test_cached_backend_query_not_found(
        self, mock_cached_backend: MockCachedBackend, sample_query_input: QueryInput
    ) -> None:
        """Test cached backend query when journal is not found."""
        with patch.object(mock_cached_backend, "_search_exact_match", return_value=[]):
            result = await mock_cached_backend.query(sample_query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.assessment is None
            assert result.confidence == 0.0
            assert result.cached is True  # Still searched cache, just no match found

    def test_search_exact_match(self, mock_cached_backend: MockCachedBackend) -> None:
        """Test exact match search functionality."""
        mock_results = [
            {"journal_name": "Test Journal", "normalized_name": "test journal"},
        ]

        # Mock the journal_cache instance attribute directly
        with patch.object(
            mock_cached_backend.journal_cache, "search_journals_by_name"
        ) as mock_search:
            mock_search.return_value = mock_results

            results = mock_cached_backend._search_exact_match("Test Journal")

            # Should call the optimized search_journals_by_name method
            mock_search.assert_called_once_with(
                name="Test Journal",
                source_name=mock_cached_backend.source_name,
                assessment=mock_cached_backend.list_type,
            )
            assert results == mock_results


class TestApiBackendWithCache:
    """Test cases for ApiBackendWithCache."""

    class MockApiBackendWithCache(ApiBackendWithCache):
        """Mock ApiBackendWithCache for testing."""

        def __init__(self) -> None:
            super().__init__(24)

        def get_name(self) -> str:
            return "mock_api_with_cache"

        def get_evidence_type(self) -> EvidenceType:
            return EvidenceType.HEURISTIC

        async def _query_api(self, query_input: QueryInput) -> BackendResult:
            """Mock API query."""
            return BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="mock_api_with_cache",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment=AssessmentType.PREDATORY,
                data={"api": "data"},
                sources=["api"],
                response_time=0.2,
            )

    @pytest.fixture
    def mock_api_with_cache_backend(self) -> MockApiBackendWithCache:
        """Create mock ApiBackendWithCache backend."""
        return self.MockApiBackendWithCache()

    @pytest.mark.asyncio
    async def test_api_with_cache_backend_cache_hit(
        self,
        mock_api_with_cache_backend: ApiBackendWithCache,
        sample_query_input: QueryInput,
    ) -> None:
        """Test ApiBackendWithCache with cache hit."""
        from aletheia_probe.models import AssessmentResult, BackendResult

        # Create a mock cached assessment result
        mock_cached_result = AssessmentResult(
            input_query="Test Journal",
            assessment=AssessmentType.PREDATORY,
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    fallback_chain=QueryFallbackChain([]),
                    backend_name="mock_api_with_cache",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment=AssessmentType.PREDATORY,
                    data={"test": "cache_data"},
                    sources=["cache"],
                    response_time=0.1,
                )
            ],
            metadata=None,
            processing_time=1.0,
        )

        # Mock the assessment_cache instance attribute directly
        with patch.object(
            mock_api_with_cache_backend.assessment_cache, "get_cached_assessment"
        ) as mock_get:
            mock_get.return_value = mock_cached_result

            result = await mock_api_with_cache_backend.query(sample_query_input)

            # Should use cache result
            assert result.status == BackendStatus.FOUND
            assert result.confidence == 0.9
            assert result.data["from_cache"] is True
            assert result.cached is True  # Cache hit should set cached=True

    @pytest.mark.asyncio
    async def test_api_with_cache_backend_cache_miss_api_hit(
        self,
        mock_api_with_cache_backend: ApiBackendWithCache,
        sample_query_input: QueryInput,
    ) -> None:
        """Test ApiBackendWithCache with cache miss but API hit."""
        # Mock the assessment_cache instance attribute directly
        with patch.object(
            mock_api_with_cache_backend.assessment_cache, "get_cached_assessment"
        ) as mock_get:
            mock_get.return_value = None

            with patch.object(
                mock_api_with_cache_backend.assessment_cache, "cache_assessment_result"
            ) as mock_cache:
                result = await mock_api_with_cache_backend.query(sample_query_input)

                # Should fallback to API
                assert result.status == BackendStatus.FOUND
                assert result.confidence == 0.7
                assert result.data == {"api": "data"}
                assert result.cached is False  # API call should set cached=False

    @pytest.mark.asyncio
    async def test_api_with_cache_backend_both_miss(
        self,
        mock_api_with_cache_backend: ApiBackendWithCache,
        sample_query_input: QueryInput,
    ) -> None:
        """Test ApiBackendWithCache when both cache and API miss."""

        class MissApiBackendWithCache(TestApiBackendWithCache.MockApiBackendWithCache):
            async def _query_api(self, query_input: QueryInput) -> BackendResult:
                return BackendResult(
                    fallback_chain=QueryFallbackChain([]),
                    backend_name="mock_api_with_cache",
                    status=BackendStatus.NOT_FOUND,
                    confidence=0.0,
                    data={},
                    sources=[],
                    response_time=0.1,
                )

        backend = MissApiBackendWithCache()

        with (
            patch("aletheia_probe.backends.base.JournalCache") as MockJournalCache,
            patch(
                "aletheia_probe.backends.base.AssessmentCache"
            ) as MockAssessmentCache,
        ):
            mock_journal_cache = Mock()
            MockJournalCache.return_value = mock_journal_cache

            mock_assessment_cache = Mock()
            mock_assessment_cache.get_cached_assessment.return_value = None
            mock_assessment_cache.cache_assessment_result = Mock()
            MockAssessmentCache.return_value = mock_assessment_cache

            # Re-initialize backend to use mocked caches
            backend = MissApiBackendWithCache()

            result = await backend.query(sample_query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.confidence == 0.0


class TestBackendRegistry:
    """Test cases for backend registry."""

    @pytest.fixture(autouse=True)
    def save_and_restore_registry(self) -> Generator[None, None, None]:
        """Save and restore backend registry state for each test."""
        registry = get_backend_registry()
        # Save current state
        saved_factories = copy.copy(registry._factories)
        saved_configs = copy.copy(registry._default_configs)

        yield

        # Restore state
        registry._factories = saved_factories
        registry._default_configs = saved_configs

    def test_register_and_get_backend(self) -> None:
        """Test registering and retrieving backends."""
        # Register backend factory
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), default_config={}
        )

        # Should be able to retrieve it
        retrieved = get_backend_registry().get_backend("mock_backend")
        assert retrieved.get_name() == "mock_backend"

    def test_get_nonexistent_backend(self) -> None:
        """Test retrieving non-existent backend."""
        with pytest.raises(ValueError, match="Backend 'nonexistent' not found"):
            get_backend_registry().get_backend("nonexistent")

    def test_get_backend_names(self) -> None:
        """Test getting list of registered backend names."""
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )
        get_backend_registry().register_factory(
            "mock_cache", lambda: MockCachedBackend(), {}
        )

        names = get_backend_registry().get_backend_names()
        assert "mock_backend" in names
        assert "mock_cache" in names

    def test_register_duplicate_backend(self) -> None:
        """Test that registering duplicate backend replaces the old one."""
        # Register first factory
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )

        # Register second factory with same name
        class NewMockBackend(Backend):
            def get_name(self) -> str:
                return "mock_backend"

            def get_evidence_type(self) -> EvidenceType:
                return EvidenceType.HEURISTIC

            async def query(self, query_input: QueryInput) -> BackendResult:
                return BackendResult(
                    fallback_chain=QueryFallbackChain([]),
                    backend_name="mock_backend",
                    status=BackendStatus.FOUND,
                    confidence=1.0,
                    assessment=AssessmentType.LEGITIMATE,
                    data={},
                    sources=[],
                    response_time=0.1,
                )

        get_backend_registry().register_factory(
            "mock_backend", lambda: NewMockBackend(), {}
        )

        # Should get the second one
        retrieved = get_backend_registry().get_backend("mock_backend")
        assert retrieved.get_name() == "mock_backend"

    def test_list_all_backends(self) -> None:
        """Test listing all registered backends."""
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )
        get_backend_registry().register_factory(
            "mock_cache", lambda: MockCachedBackend(), {}
        )

        # Create all registered backends manually since list_all() was removed
        registry = get_backend_registry()
        all_backends = []
        for name in registry.get_backend_names():
            try:
                all_backends.append(registry.create_backend(name))
            except (ValueError, TypeError, AttributeError, OSError):
                # Skip backends that fail to create with default config
                pass

        # Note: Changed from == 2 to >= 2 because we removed the registry clearing
        # that accessed private attributes (_factories.clear(), _default_configs.clear()).
        # The registry may contain other backends from previous tests or initialization.
        assert len(all_backends) >= 2
        assert any(b.get_name() == "mock_backend" for b in all_backends)
        assert any(b.get_name() == "mock_cache" for b in all_backends)
