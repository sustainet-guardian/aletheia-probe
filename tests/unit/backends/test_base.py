# SPDX-License-Identifier: MIT
"""Tests for the base backend functionality."""

import asyncio
import copy
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.backends.base import (
    Backend,
    CachedBackend,
    HybridBackend,
    get_backend_registry,
)
from aletheia_probe.enums import EvidenceType
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput


class MockBackend(Backend):
    """Mock backend for testing."""

    def __init__(self):
        super().__init__()

    async def query(self, query_input: QueryInput) -> BackendResult:
        """Mock query implementation."""
        return BackendResult(
            backend_name="mock_backend",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment="predatory",
            data={"test": "data"},
            sources=["test_source"],
            response_time=0.1,
        )

    def get_name(self) -> str:
        return "mock_backend"

    def get_description(self) -> str:
        return "Mock backend for testing"

    def get_evidence_type(self) -> EvidenceType:
        return EvidenceType.HEURISTIC


class MockCachedBackend(CachedBackend):
    """Mock cached backend for testing."""

    def __init__(self):
        super().__init__("mock_cache", "predatory")

    def get_name(self) -> str:
        return "mock_cache"

    def get_description(self) -> str:
        return "Mock cached backend for testing"


class TestBackendBase:
    """Test cases for Backend base class."""

    @pytest.mark.asyncio
    async def test_query_with_timeout_success(self):
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
    async def test_query_with_timeout_timeout(self):
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
    async def test_query_with_timeout_exception(self):
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
    def mock_cached_backend(self):
        """Create mock cached backend."""
        return MockCachedBackend()

    @pytest.mark.asyncio
    async def test_cached_backend_query_found(
        self, mock_cached_backend, sample_query_input
    ):
        """Test cached backend query when journal is found."""
        mock_results = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test journal",
                "issn": "1234-5678",
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
            assert result.assessment == "predatory"
            assert result.confidence == 0.9
            assert result.cached is True  # CachedBackend always returns cached=True

    @pytest.mark.asyncio
    async def test_cached_backend_query_not_found(
        self, mock_cached_backend, sample_query_input
    ):
        """Test cached backend query when journal is not found."""
        with patch.object(mock_cached_backend, "_search_exact_match", return_value=[]):
            result = await mock_cached_backend.query(sample_query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.assessment is None
            assert result.confidence == 0.0
            assert result.cached is True  # Still searched cache, just no match found

    def test_search_exact_match(self, mock_cached_backend):
        """Test exact match search functionality."""
        mock_results = [
            {"journal_name": "Test Journal", "normalized_name": "test journal"},
        ]

        with patch(
            "aletheia_probe.backends.base.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.search_journals_by_name.return_value = mock_results
            mock_get_cache_manager.return_value = mock_cache

            results = mock_cached_backend._search_exact_match("Test Journal")

            # Should call the optimized search_journals_by_name method
            mock_cache.search_journals_by_name.assert_called_once_with(
                name="Test Journal",
                source_name=mock_cached_backend.source_name,
                assessment=mock_cached_backend.list_type,
            )
            assert results == mock_results

    def test_calculate_confidence_issn_match(self, mock_cached_backend):
        """Test confidence calculation with ISSN match."""
        query_input = QueryInput(
            raw_input="Test Journal",
            normalized_name="test journal",
            identifiers={"issn": "1234-5678"},
        )

        match = {
            "journal_name": "Test Journal",
            "issn": "1234-5678",
            "normalized_name": "test journal",
        }

        confidence = mock_cached_backend._calculate_confidence(query_input, match)

        # Should have high confidence for ISSN match
        assert confidence >= 0.9

    def test_calculate_confidence_name_match(self, mock_cached_backend):
        """Test confidence calculation with name match only."""
        query_input = QueryInput(
            raw_input="Test Journal", normalized_name="test journal"
        )

        match = {"journal_name": "Test Journal", "normalized_name": "test journal"}

        confidence = mock_cached_backend._calculate_confidence(query_input, match)

        # Should have good confidence for exact name match
        assert confidence >= 0.8

    def test_calculate_confidence_partial_match(self, mock_cached_backend):
        """Test confidence calculation with partial match."""
        query_input = QueryInput(
            raw_input="Test Journal of Science",
            normalized_name="test journal of science",
        )

        match = {"journal_name": "Test Journal", "normalized_name": "test journal"}

        confidence = mock_cached_backend._calculate_confidence(query_input, match)

        # Should have low to moderate confidence for partial match
        assert 0.3 <= confidence < 0.8


class TestHybridBackend:
    """Test cases for HybridBackend."""

    class MockHybridBackend(HybridBackend):
        """Mock hybrid backend for testing."""

        def __init__(self):
            super().__init__(24)

        def get_name(self) -> str:
            return "mock_hybrid"

        async def _query_api(self, query_input: QueryInput) -> BackendResult:
            """Mock API query."""
            return BackendResult(
                backend_name="mock_hybrid",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment="predatory",
                data={"api": "data"},
                sources=["api"],
                response_time=0.2,
            )

        def get_description(self) -> str:
            return "Mock hybrid backend"

    @pytest.fixture
    def mock_hybrid_backend(self):
        """Create mock hybrid backend."""
        return self.MockHybridBackend()

    @pytest.mark.asyncio
    async def test_hybrid_backend_cache_hit(
        self, mock_hybrid_backend, sample_query_input
    ):
        """Test hybrid backend with cache hit."""
        from aletheia_probe.models import AssessmentResult, BackendResult

        # Create a mock cached assessment result
        mock_cached_result = AssessmentResult(
            input_query="Test Journal",
            assessment="predatory",
            confidence=0.9,
            overall_score=0.9,
            backend_results=[
                BackendResult(
                    backend_name="mock_hybrid",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment="predatory",
                    data={"test": "cache_data"},
                    sources=["cache"],
                    response_time=0.1,
                )
            ],
            metadata=None,
            processing_time=1.0,
        )

        with patch(
            "aletheia_probe.backends.base.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.get_cached_assessment.return_value = mock_cached_result
            mock_get_cache_manager.return_value = mock_cache

            result = await mock_hybrid_backend.query(sample_query_input)

            # Should use cache result
            assert result.status == BackendStatus.FOUND
            assert result.confidence == 0.9
            assert result.data["from_cache"] is True
            assert result.cached is True  # Cache hit should set cached=True

    @pytest.mark.asyncio
    async def test_hybrid_backend_cache_miss_api_hit(
        self, mock_hybrid_backend, sample_query_input
    ):
        """Test hybrid backend with cache miss but API hit."""
        with patch(
            "aletheia_probe.backends.base.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.get_cached_assessment.return_value = None
            mock_cache.cache_assessment_result = Mock()
            mock_get_cache_manager.return_value = mock_cache

            result = await mock_hybrid_backend.query(sample_query_input)

            # Should fallback to API
            assert result.status == BackendStatus.FOUND
            assert result.confidence == 0.7
            assert result.data == {"api": "data"}
            assert result.cached is False  # API call should set cached=False

    @pytest.mark.asyncio
    async def test_hybrid_backend_both_miss(
        self, mock_hybrid_backend, sample_query_input
    ):
        """Test hybrid backend when both cache and API miss."""

        class MissHybridBackend(TestHybridBackend.MockHybridBackend):
            async def _query_api(self, query_input: QueryInput) -> BackendResult:
                return BackendResult(
                    backend_name="mock_hybrid",
                    status=BackendStatus.NOT_FOUND,
                    confidence=0.0,
                    assessment=None,
                    data={},
                    sources=[],
                    response_time=0.1,
                )

        backend = MissHybridBackend()

        with patch(
            "aletheia_probe.backends.base.get_cache_manager"
        ) as mock_get_cache_manager:
            mock_cache = Mock()
            mock_cache.get_cached_assessment.return_value = None
            mock_cache.cache_assessment_result = Mock()
            mock_get_cache_manager.return_value = mock_cache

            result = await backend.query(sample_query_input)

            assert result.status == BackendStatus.NOT_FOUND
            assert result.confidence == 0.0


class TestBackendRegistry:
    """Test cases for backend registry."""

    @pytest.fixture(autouse=True)
    def save_and_restore_registry(self):
        """Save and restore backend registry state for each test."""
        registry = get_backend_registry()
        # Save current state
        saved_factories = copy.copy(registry._factories)
        saved_configs = copy.copy(registry._default_configs)

        yield

        # Restore state
        registry._factories = saved_factories
        registry._default_configs = saved_configs

    def test_register_and_get_backend(self):
        """Test registering and retrieving backends."""
        # Register backend factory
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), default_config={}
        )

        # Should be able to retrieve it
        retrieved = get_backend_registry().get_backend("mock_backend")
        assert retrieved.get_name() == "mock_backend"

    def test_get_nonexistent_backend(self):
        """Test retrieving non-existent backend."""
        with pytest.raises(ValueError, match="Backend 'nonexistent' not found"):
            get_backend_registry().get_backend("nonexistent")

    def test_get_backend_names(self):
        """Test getting list of registered backend names."""
        # Clear registry first
        get_backend_registry()._factories.clear()
        get_backend_registry()._default_configs.clear()

        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )
        get_backend_registry().register_factory(
            "mock_cache", lambda: MockCachedBackend(), {}
        )

        names = get_backend_registry().get_backend_names()
        assert "mock_backend" in names
        assert "mock_cache" in names

    def test_register_duplicate_backend(self):
        """Test that registering duplicate backend replaces the old one."""
        # Register first factory
        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )

        # Register second factory with same name
        class NewMockBackend(Backend):
            def get_name(self) -> str:
                return "mock_backend"

            def get_description(self) -> str:
                return "New mock backend"

            def get_evidence_type(self) -> EvidenceType:
                return EvidenceType.HEURISTIC

            async def query(self, query_input):
                return BackendResult(
                    backend_name="mock_backend",
                    status=BackendStatus.FOUND,
                    confidence=1.0,
                    assessment="new",
                    data={},
                    sources=[],
                    response_time=0.1,
                )

        get_backend_registry().register_factory(
            "mock_backend", lambda: NewMockBackend(), {}
        )

        # Should get the second one
        retrieved = get_backend_registry().get_backend("mock_backend")
        assert retrieved.get_description() == "New mock backend"

    def test_list_all_backends(self):
        """Test listing all registered backends."""
        # Clear factory registrations for isolated testing
        get_backend_registry()._factories.clear()
        get_backend_registry()._default_configs.clear()

        get_backend_registry().register_factory(
            "mock_backend", lambda: MockBackend(), {}
        )
        get_backend_registry().register_factory(
            "mock_cache", lambda: MockCachedBackend(), {}
        )

        all_backends = get_backend_registry().list_all()
        assert len(all_backends) == 2
        assert any(b.get_name() == "mock_backend" for b in all_backends)
        assert any(b.get_name() == "mock_cache" for b in all_backends)
