# SPDX-License-Identifier: MIT
"""Basic integration tests for the journal assessment tool.

INTEGRATION TEST FILE: This file contains integration tests that verify
component interactions and end-to-end workflows. These are NOT predictable
unit tests - they may make real external API calls and use fuzzy assertions.

See README.md in this directory for details on integration test characteristics
and how to interpret test failures.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aletheia_probe.dispatcher import QueryDispatcher
from aletheia_probe.enums import EvidenceType
from aletheia_probe.models import BackendResult, BackendStatus, QueryInput
from aletheia_probe.normalizer import InputNormalizer


class TestBasicIntegration:
    """Basic integration tests."""

    def test_normalizer_integration(self):
        """Test input normalizer integration."""
        normalizer = InputNormalizer()

        # Test basic normalization
        result = normalizer.normalize("Journal of Computer Science")
        assert isinstance(result, QueryInput)
        assert result.raw_input == "Journal of Computer Science"
        assert result.normalized_name is not None

    def test_normalizer_with_issn(self):
        """Test normalizer with ISSN extraction."""
        normalizer = InputNormalizer()

        result = normalizer.normalize("Nature (ISSN: 0028-0836)")
        assert result.identifiers.get("issn") == "0028-0836"

    @pytest.mark.asyncio
    async def test_dispatcher_integration_mocked(self):
        """Test dispatcher integration with mocked backends."""
        with (
            patch(
                "aletheia_probe.dispatcher.get_config_manager"
            ) as mock_get_config_manager,
            patch("aletheia_probe.dispatcher.get_detail_logger"),
        ):
            # Setup mocks

            # Mock config manager to return proper backend config
            mock_backend_config = Mock()
            mock_backend_config.weight = 0.8
            mock_config_manager = Mock()
            mock_config_manager.get_backend_config.return_value = mock_backend_config
            mock_get_config_manager.return_value = mock_config_manager

            dispatcher = QueryDispatcher()

            # Create a mock backend
            mock_backend = Mock()
            mock_backend.get_name.return_value = "test_backend"
            mock_backend.get_evidence_type.return_value = EvidenceType.PREDATORY_LIST
            mock_backend.weight = 0.8  # Add weight attribute
            mock_backend.query_with_timeout = AsyncMock(
                return_value=BackendResult(
                    backend_name="test_backend",
                    status=BackendStatus.FOUND,
                    confidence=0.9,
                    assessment="predatory",
                    data={"test": "data"},
                    sources=["test_source"],
                    response_time=0.1,
                    evidence_type=EvidenceType.PREDATORY_LIST.value,
                )
            )

            with patch.object(
                dispatcher, "_get_enabled_backends", return_value=[mock_backend]
            ):
                query_input = QueryInput(
                    raw_input="Test Journal", normalized_name="test journal"
                )

                result = await dispatcher.assess_journal(query_input)

                assert result.assessment == "predatory"
                assert result.confidence > 0.8
                assert len(result.backend_results) == 1

    def test_config_integration(self):
        """Test configuration integration."""
        from aletheia_probe.config import ConfigManager

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
backends:
  test_backend:
    name: test_backend
    enabled: true
    weight: 0.8
    timeout: 10
"""
            )
            config_path = Path(f.name)

        try:
            manager = ConfigManager(config_path)
            config = manager.load_config()

            assert "test_backend" in config.backends
            assert config.backends["test_backend"].enabled
            assert config.backends["test_backend"].weight == 0.8

        finally:
            config_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_end_to_end_flow_mocked(self):
        """Test end-to-end flow with mocked components."""
        from aletheia_probe.dispatcher import QueryDispatcher
        from aletheia_probe.normalizer import InputNormalizer

        # Mock all external dependencies
        with (
            patch(
                "aletheia_probe.dispatcher.get_config_manager"
            ) as mock_get_config_manager,
            patch("aletheia_probe.dispatcher.get_detail_logger"),
        ):
            # Create components
            normalizer = InputNormalizer()

            # Mock config manager to return proper backend config
            mock_backend_config = Mock()
            mock_backend_config.weight = 0.8
            mock_config_manager = Mock()
            mock_config_manager.get_backend_config.return_value = mock_backend_config
            mock_get_config_manager.return_value = mock_config_manager

            dispatcher = QueryDispatcher()

            # Setup mock backend
            mock_backend = Mock()
            mock_backend.get_name.return_value = "integration_test_backend"
            mock_backend.get_evidence_type.return_value = EvidenceType.LEGITIMATE_LIST
            mock_backend.weight = 0.8  # Add weight attribute
            mock_backend.query_with_timeout = AsyncMock(
                return_value=BackendResult(
                    backend_name="integration_test_backend",
                    status=BackendStatus.FOUND,
                    confidence=0.85,
                    assessment="legitimate",
                    data={"source": "integration_test"},
                    sources=["test_database"],
                    response_time=0.2,
                    evidence_type=EvidenceType.LEGITIMATE_LIST.value,
                )
            )

            with patch.object(
                dispatcher, "_get_enabled_backends", return_value=[mock_backend]
            ):
                # 1. Normalize input
                query_input = normalizer.normalize("Journal of Software Engineering")

                # 2. Assess journal
                result = await dispatcher.assess_journal(query_input)

                # 3. Verify results
                assert result.input_query == "Journal of Software Engineering"
                assert result.assessment == "legitimate"
                assert result.confidence > 0.8
                assert len(result.backend_results) == 1
                assert result.processing_time > 0

    def test_model_serialization(self):
        """Test that models can be serialized/deserialized."""
        from aletheia_probe.models import (
            AssessmentResult,
            BackendResult,
            BackendStatus,
        )

        # Create test data
        backend_result = BackendResult(
            backend_name="test_backend",
            status=BackendStatus.FOUND,
            confidence=0.9,
            assessment="predatory",
            data={"key": "value"},
            sources=["source1", "source2"],
            response_time=0.15,
            evidence_type=EvidenceType.PREDATORY_LIST.value,
        )

        assessment_result = AssessmentResult(
            input_query="Test Journal",
            assessment="predatory",
            confidence=0.85,
            overall_score=0.9,
            backend_results=[backend_result],
            metadata=None,
            reasoning=["Found in predatory database"],
            processing_time=1.2,
        )

        # Test serialization
        serialized = assessment_result.model_dump()
        assert isinstance(serialized, dict)
        assert serialized["assessment"] == "predatory"
        assert len(serialized["backend_results"]) == 1

        # Test that we can recreate from dict
        recreated = AssessmentResult.model_validate(serialized)
        assert recreated.assessment == "predatory"
        assert recreated.confidence == 0.85

    def test_error_handling_integration(self):
        """Test error handling across components."""
        from aletheia_probe.normalizer import InputNormalizer

        normalizer = InputNormalizer()

        # Test with invalid input - normalizer raises error on empty strings
        with pytest.raises(ValueError):
            normalizer.normalize("")  # Empty string should raise error

        # Test with very long input - normalizer handles this gracefully
        result = normalizer.normalize("x" * 1000)  # Very long string
        assert result.raw_input == "x" * 1000

    @pytest.mark.asyncio
    async def test_concurrent_assessments(self):
        """Test that concurrent assessments work properly."""
        with (
            patch(
                "aletheia_probe.dispatcher.get_config_manager"
            ) as mock_get_config_manager,
            patch("aletheia_probe.dispatcher.get_detail_logger"),
        ):
            # Mock config manager to return proper backend config
            mock_backend_config = Mock()
            mock_backend_config.weight = 0.8
            mock_config_manager = Mock()
            mock_config_manager.get_backend_config.return_value = mock_backend_config
            mock_get_config_manager.return_value = mock_config_manager

            dispatcher = QueryDispatcher()

            # Setup mock backend
            mock_backend = Mock()
            mock_backend.get_name.return_value = "concurrent_test_backend"
            mock_backend.get_evidence_type.return_value = EvidenceType.PREDATORY_LIST
            mock_backend.weight = 0.8  # Add weight attribute
            mock_backend.query_with_timeout = AsyncMock(
                return_value=BackendResult(
                    backend_name="concurrent_test_backend",
                    status=BackendStatus.FOUND,
                    confidence=0.8,
                    assessment="predatory",
                    data={},
                    sources=["test"],
                    response_time=0.1,
                    evidence_type=EvidenceType.PREDATORY_LIST.value,
                )
            )

            with patch.object(
                dispatcher, "_get_enabled_backends", return_value=[mock_backend]
            ):
                # Create multiple concurrent assessment tasks
                tasks = []
                for i in range(5):
                    query_input = QueryInput(
                        raw_input=f"Test Journal {i}",
                        normalized_name=f"test journal {i}",
                    )
                    task = dispatcher.assess_journal(query_input)
                    tasks.append(task)

                # Wait for all assessments to complete
                results = await asyncio.gather(*tasks)

                # Verify all completed successfully
                assert len(results) == 5
                for result in results:
                    assert result.assessment == "predatory"
                    assert (
                        abs(result.confidence - 0.8) < 0.01
                    )  # Allow for floating point precision
