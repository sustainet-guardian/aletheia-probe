# SPDX-License-Identifier: MIT
"""Tests for the query dispatcher module."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.dispatcher import QueryDispatcher
from aletheia_probe.enums import AssessmentType, EvidenceType
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    QueryInput,
)


@pytest.fixture
def dispatcher():
    """Create a QueryDispatcher instance for testing."""
    with (
        patch(
            "aletheia_probe.dispatcher.get_config_manager"
        ) as mock_get_config_manager,
        patch("aletheia_probe.dispatcher.get_detail_logger"),
    ):
        # Configure the mock to return proper backend config
        mock_backend_config = Mock()
        mock_backend_config.weight = 1.0
        mock_backend_config.timeout = 10
        mock_backend_config.email = None
        mock_backend_config.config = {}
        mock_config_manager = Mock()
        mock_config_manager.get_backend_config.return_value = mock_backend_config
        mock_get_config_manager.return_value = mock_config_manager
        return QueryDispatcher()


@pytest.fixture
def mock_backend():
    """Create a mock backend for testing."""
    backend = Mock()
    backend.get_name.return_value = "test_backend"
    backend.get_evidence_type.return_value = EvidenceType.PREDATORY_LIST
    backend.query_with_timeout = AsyncMock(
        return_value=BackendResult(
            backend_name="test_backend",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.PREDATORY,
            data={"test": "data"},
            sources=["test_source"],
            response_time=0.1,
            evidence_type=EvidenceType.PREDATORY_LIST.value,
        )
    )
    return backend


class TestQueryDispatcher:
    """Test cases for QueryDispatcher."""

    @pytest.mark.asyncio
    async def test_assess_journal_basic_flow(
        self, dispatcher, sample_query_input, mock_backend
    ):
        """Test basic journal assessment flow."""
        with patch.object(
            dispatcher, "_get_enabled_backends", return_value=[mock_backend]
        ):
            result = await dispatcher.assess_journal(sample_query_input)

            assert isinstance(result, AssessmentResult)
            assert result.input_query == sample_query_input.raw_input
            assert result.assessment == AssessmentType.PREDATORY
            assert result.confidence == 0.8
            assert result.processing_time > 0
            assert len(result.backend_results) == 1

    @pytest.mark.asyncio
    async def test_assess_journal_no_backends(self, dispatcher, sample_query_input):
        """Test assessment with no enabled backends."""
        with patch.object(dispatcher, "_get_enabled_backends", return_value=[]):
            result = await dispatcher.assess_journal(sample_query_input)

            assert result.assessment == AssessmentType.UNKNOWN
            assert result.confidence == 0.0
            assert result.overall_score == 0.0
            assert len(result.backend_results) == 0
            assert "No backends available for assessment" in result.reasoning

    @pytest.mark.asyncio
    async def test_assess_journal_backend_error(self, dispatcher, sample_query_input):
        """Test assessment when backend raises an error."""
        error_backend = Mock()
        error_backend.get_name.return_value = "error_backend"
        error_backend.query_with_timeout = AsyncMock(
            side_effect=Exception("Test error")
        )

        with patch.object(
            dispatcher, "_get_enabled_backends", return_value=[error_backend]
        ):
            result = await dispatcher.assess_journal(sample_query_input)

            assert len(result.backend_results) == 1
            backend_result = result.backend_results[0]
            assert backend_result.status == BackendStatus.ERROR
            assert "Test error" in backend_result.error_message

    @pytest.mark.asyncio
    async def test_assess_journal_multiple_backends(
        self, dispatcher, sample_query_input
    ):
        """Test assessment with multiple backends."""
        predatory_backend = Mock()
        predatory_backend.get_name.return_value = "predatory_backend"
        predatory_backend.get_evidence_type.return_value = EvidenceType.PREDATORY_LIST
        predatory_backend.query_with_timeout = AsyncMock(
            return_value=BackendResult(
                backend_name="predatory_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=AssessmentType.PREDATORY,
                data={},
                sources=["source1"],
                response_time=0.1,
                evidence_type=EvidenceType.PREDATORY_LIST.value,
            )
        )

        legitimate_backend = Mock()
        legitimate_backend.get_name.return_value = "legitimate_backend"
        legitimate_backend.get_evidence_type.return_value = EvidenceType.LEGITIMATE_LIST
        legitimate_backend.query_with_timeout = AsyncMock(
            return_value=BackendResult(
                backend_name="legitimate_backend",
                status=BackendStatus.FOUND,
                confidence=0.7,
                assessment=AssessmentType.LEGITIMATE,
                data={},
                sources=["source2"],
                response_time=0.1,
                evidence_type=EvidenceType.LEGITIMATE_LIST.value,
            )
        )

        backends = [predatory_backend, legitimate_backend]

        with (
            patch.object(dispatcher, "_get_enabled_backends", return_value=backends),
            patch.object(
                dispatcher.config_manager,
                "get_backend_config",
                return_value=Mock(weight=1.0),
            ),
        ):
            result = await dispatcher.assess_journal(sample_query_input)

            assert len(result.backend_results) == 2
            assert result.assessment == AssessmentType.PREDATORY
            assert result.confidence == 0.45

    @pytest.mark.asyncio
    async def test_assess_journal_with_retraction_data(
        self, dispatcher, sample_query_input
    ):
        """Test assessment with retraction watch data."""
        retraction_backend = Mock()
        retraction_backend.get_name.return_value = "retraction_watch"
        retraction_backend.get_evidence_type.return_value = EvidenceType.HEURISTIC
        retraction_backend.query_with_timeout = AsyncMock(
            return_value=BackendResult(
                backend_name="retraction_watch",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment=AssessmentType.LEGITIMATE,
                data={
                    "risk_level": "high",
                    "total_retractions": 15,
                    "recent_retractions": 5,
                    "has_publication_data": True,
                    "retraction_rate": 2.5,
                    "total_publications": 600,
                },
                sources=["retraction_watch"],
                response_time=0.1,
                evidence_type=EvidenceType.HEURISTIC.value,
            )
        )

        with (
            patch.object(
                dispatcher, "_get_enabled_backends", return_value=[retraction_backend]
            ),
            patch.object(
                dispatcher.config_manager,
                "get_backend_config",
                return_value=Mock(weight=1.0),
            ),
        ):
            result = await dispatcher.assess_journal(sample_query_input)

            # Check that retraction information appears in reasoning
            reasoning_text = " ".join(result.reasoning)
            assert "retraction" in reasoning_text.lower()
            assert "HIGH" in reasoning_text or "high" in reasoning_text

    def test_get_enabled_backends(self, dispatcher):
        """Test getting enabled backends."""
        with (
            patch.object(
                dispatcher.config_manager,
                "get_enabled_backends",
                return_value=["backend1", "backend2"],
            ),
            patch(
                "aletheia_probe.dispatcher.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_backend1 = Mock()
            mock_backend2 = Mock()
            mock_registry = Mock()
            mock_registry.get_backend.side_effect = [mock_backend1, mock_backend2]
            mock_get_registry.return_value = mock_registry

            backends = dispatcher._get_enabled_backends()

            assert len(backends) == 2
            assert mock_backend1 in backends
            assert mock_backend2 in backends

    def test_get_enabled_backends_with_missing_backend(self, dispatcher):
        """Test getting enabled backends when one is not registered."""
        with (
            patch.object(
                dispatcher.config_manager,
                "get_enabled_backends",
                return_value=["backend1", "missing_backend"],
            ),
            patch(
                "aletheia_probe.dispatcher.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_backend1 = Mock()
            mock_registry = Mock()
            mock_registry.get_backend.side_effect = [
                mock_backend1,
                ValueError("Backend not found"),
            ]
            mock_get_registry.return_value = mock_registry

            backends = dispatcher._get_enabled_backends()

            assert len(backends) == 1
            assert mock_backend1 in backends

    def test_get_enabled_backends_no_config(self, dispatcher):
        """Test getting backends when none are configured."""
        with (
            patch.object(
                dispatcher.config_manager, "get_enabled_backends", return_value=[]
            ),
            patch(
                "aletheia_probe.dispatcher.get_backend_registry"
            ) as mock_get_registry,
        ):
            mock_registry = Mock()
            mock_registry.get_backend_names.return_value = ["default1", "default2"]
            mock_backend1 = Mock()
            mock_backend2 = Mock()
            mock_registry.get_backend.side_effect = [mock_backend1, mock_backend2]
            mock_get_registry.return_value = mock_registry

            backends = dispatcher._get_enabled_backends()

            assert len(backends) == 2

    @pytest.mark.asyncio
    async def test_query_backends_timeout(self, dispatcher, sample_query_input):
        """Test backend querying with timeout."""
        slow_backend = Mock()
        slow_backend.get_name.return_value = "slow_backend"
        slow_backend.get_evidence_type.return_value = EvidenceType.HEURISTIC
        slow_backend.query_with_timeout = AsyncMock(
            return_value=BackendResult(
                backend_name="slow_backend",
                status=BackendStatus.TIMEOUT,
                confidence=0.0,
                assessment=None,
                data={},
                sources=[],
                error_message="Timeout",
                response_time=10.0,
                evidence_type=EvidenceType.HEURISTIC.value,
            )
        )

        with patch.object(
            dispatcher.config_manager,
            "get_backend_config",
            return_value=Mock(timeout=5),
        ):
            results = await dispatcher._query_backends(
                [slow_backend], sample_query_input
            )

            assert len(results) == 1
            assert results[0].status == BackendStatus.TIMEOUT

    def test_calculate_assessment_predatory_classification(
        self, dispatcher, sample_query_input
    ):
        """Test assessment calculation for predatory classification."""
        predatory_result = BackendResult(
            backend_name="test_backend",
            status=BackendStatus.FOUND,
            confidence=0.9,
            assessment=AssessmentType.PREDATORY,
            data={},
            sources=[],
            response_time=0.1,
            evidence_type=EvidenceType.HEURISTIC.value,
        )

        with patch.object(
            dispatcher.config_manager,
            "get_backend_config",
            return_value=Mock(weight=1.0),
        ):
            result = dispatcher._calculate_assessment(
                sample_query_input, [predatory_result], 1.0
            )

            assert result.assessment == AssessmentType.SUSPICIOUS
            assert result.confidence > 0.8
            assert "suspicious" in " ".join(result.reasoning).lower()

    def test_calculate_assessment_legitimate_classification(
        self, dispatcher, sample_query_input
    ):
        """Test assessment calculation for legitimate classification."""
        legitimate_result = BackendResult(
            backend_name="test_backend",
            status=BackendStatus.FOUND,
            confidence=0.85,
            assessment=AssessmentType.LEGITIMATE,
            data={},
            sources=[],
            response_time=0.1,
            evidence_type=EvidenceType.LEGITIMATE_LIST.value,
        )

        with patch.object(
            dispatcher.config_manager,
            "get_backend_config",
            return_value=Mock(weight=1.0),
        ):
            result = dispatcher._calculate_assessment(
                sample_query_input, [legitimate_result], 1.0
            )

            assert result.assessment == AssessmentType.LEGITIMATE
            assert result.confidence > 0.7
            assert "legitimate" in " ".join(result.reasoning).lower()

    def test_calculate_assessment_insufficient_data(
        self, dispatcher, sample_query_input
    ):
        """Test assessment calculation when no successful results."""
        error_result = BackendResult(
            backend_name="test_backend",
            status=BackendStatus.ERROR,
            confidence=0.0,
            assessment=None,
            data={},
            sources=[],
            error_message="Test error",
            response_time=0.1,
            evidence_type=EvidenceType.HEURISTIC.value,
        )

        result = dispatcher._calculate_assessment(
            sample_query_input, [error_result], 1.0
        )

        assert result.assessment == AssessmentType.UNKNOWN
        assert result.confidence <= 0.2
        assert "error" in " ".join(result.reasoning).lower()

    @pytest.mark.asyncio
    async def test_cache_sync_error_handling(
        self, dispatcher, sample_query_input, mock_backend
    ):
        """Test assessment with backend."""
        with patch.object(
            dispatcher, "_get_enabled_backends", return_value=[mock_backend]
        ):
            # Should not raise exception
            result = await dispatcher.assess_journal(sample_query_input)

            assert isinstance(result, AssessmentResult)
            assert len(result.backend_results) == 1

    def test_get_enabled_backends_with_email_config(self, dispatcher):
        """Test getting enabled backends with email configuration."""
        with (
            patch.object(
                dispatcher.config_manager,
                "get_enabled_backends",
                return_value=["crossref_analyzer"],
            ),
            patch.object(
                dispatcher.config_manager, "get_backend_config"
            ) as mock_get_backend_config,
            patch(
                "aletheia_probe.dispatcher.get_backend_registry"
            ) as mock_get_registry,
        ):
            # Configure mock backend config with email
            mock_backend_config = Mock()
            mock_backend_config.email = "test@example.com"
            mock_backend_config.config = {}
            mock_get_backend_config.return_value = mock_backend_config

            # Configure mock registry to support factory creation
            mock_backend = Mock()
            mock_backend.get_name.return_value = "crossref_analyzer"
            mock_registry = Mock()
            mock_registry.create_backend.return_value = mock_backend
            mock_get_registry.return_value = mock_registry

            backends = dispatcher._get_enabled_backends()

            assert len(backends) == 1
            assert mock_backend in backends
            # Verify that create_backend was called with email config
            mock_registry.create_backend.assert_called_once_with(
                "crossref_analyzer", email="test@example.com"
            )

    def test_get_enabled_backends_without_email_config(self, dispatcher):
        """Test getting enabled backends without email configuration."""
        with (
            patch.object(
                dispatcher.config_manager,
                "get_enabled_backends",
                return_value=["doaj"],
            ),
            patch.object(
                dispatcher.config_manager, "get_backend_config"
            ) as mock_get_backend_config,
            patch(
                "aletheia_probe.dispatcher.get_backend_registry"
            ) as mock_get_registry,
        ):
            # Configure mock backend config without email
            mock_backend_config = Mock()
            mock_backend_config.email = None
            mock_backend_config.config = {}
            mock_get_backend_config.return_value = mock_backend_config

            # Configure mock registry
            mock_backend = Mock()
            mock_backend.get_name.return_value = "doaj"
            mock_registry = Mock()
            mock_registry.get_backend.return_value = mock_backend
            mock_get_registry.return_value = mock_registry

            backends = dispatcher._get_enabled_backends()

            assert len(backends) == 1
            assert mock_backend in backends
            # Verify that get_backend was called (not create_backend)
            mock_registry.get_backend.assert_called_once_with("doaj")
            mock_registry.create_backend.assert_not_called()
