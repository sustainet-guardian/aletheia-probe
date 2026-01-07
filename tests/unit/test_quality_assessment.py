# SPDX-License-Identifier: MIT
"""Tests for the QualityAssessmentProcessor."""

import pytest

from aletheia_probe.enums import EvidenceType
from aletheia_probe.fallback_chain import QueryFallbackChain
from aletheia_probe.models import BackendResult, BackendStatus
from aletheia_probe.quality_assessment import QualityAssessmentProcessor


class TestQualityAssessmentProcessor:
    """Test cases for QualityAssessmentProcessor."""

    @pytest.fixture
    def processor(self) -> QualityAssessmentProcessor:
        """Create a QualityAssessmentProcessor instance."""
        return QualityAssessmentProcessor()

    def test_extract_quality_data_with_critical_risk(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction of quality data with critical risk level."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={
                    "risk_level": "critical",
                    "total_retractions": 50,
                    "recent_retractions": 10,
                    "has_publication_data": True,
                    "retraction_rate": 2.5,
                    "total_publications": 2000,
                },
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {"risk_level": "critical", "total_retractions": 50}
        assert len(reasoning) == 1
        assert "CRITICAL retraction risk" in reasoning[0]
        assert "50 retractions" in reasoning[0]
        assert "10 recent" in reasoning[0]
        assert "2.500% rate" in reasoning[0]
        assert "2,000 total publications" in reasoning[0]

    def test_extract_quality_data_with_high_risk_no_publication_data(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction with high risk but no publication data."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={
                    "risk_level": "high",
                    "total_retractions": 25,
                    "recent_retractions": 5,
                    "has_publication_data": False,
                },
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {"risk_level": "high", "total_retractions": 25}
        assert len(reasoning) == 1
        assert "HIGH retraction risk" in reasoning[0]
        assert "25 total retractions" in reasoning[0]
        assert "5 recent" in reasoning[0]
        assert "%" not in reasoning[0]  # No rate without publication data

    def test_extract_quality_data_with_moderate_risk(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction with moderate risk level."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={
                    "risk_level": "moderate",
                    "total_retractions": 10,
                    "recent_retractions": 2,
                    "has_publication_data": True,
                    "retraction_rate": 0.5,
                    "total_publications": 2000,
                },
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {"risk_level": "moderate", "total_retractions": 10}
        assert len(reasoning) == 1
        assert "Moderate retraction risk" in reasoning[0]
        assert "10 retractions" in reasoning[0]
        assert "0.500% rate" in reasoning[0]

    def test_extract_quality_data_with_low_retractions(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction with low retraction count."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={
                    "risk_level": "low",
                    "total_retractions": 3,
                    "recent_retractions": 1,
                    "has_publication_data": True,
                    "retraction_rate": 0.15,
                    "total_publications": 2000,
                },
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {"risk_level": "low", "total_retractions": 3}
        assert len(reasoning) == 1
        assert "3 retraction(s)" in reasoning[0]
        assert "0.150% rate" in reasoning[0]
        assert "within normal range" in reasoning[0]

    def test_extract_quality_data_no_quality_backend(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction when no quality indicator backend is present."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="other_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={},
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.PREDATORY_LIST.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {}
        assert len(reasoning) == 0

    def test_extract_quality_data_quality_backend_not_found(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction when quality backend status is NOT_FOUND."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={},
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {}
        assert len(reasoning) == 0

    def test_extract_quality_data_empty_data(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction when quality backend has empty data."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={},
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {}
        assert len(reasoning) == 0

    def test_extract_quality_data_zero_retractions(
        self, processor: QualityAssessmentProcessor
    ) -> None:
        """Test extraction with zero retractions."""
        reasoning: list[str] = []
        backend_results = [
            BackendResult(
                fallback_chain=QueryFallbackChain([]),
                backend_name="test_quality_backend",
                status=BackendStatus.FOUND,
                confidence=0.9,
                assessment=None,
                data={
                    "risk_level": "none",
                    "total_retractions": 0,
                    "recent_retractions": 0,
                },
                sources=["test_source"],
                error_message=None,
                response_time=0.1,
                cached=False,
                execution_time_ms=100.0,
                evidence_type=EvidenceType.QUALITY_INDICATOR.value,
            )
        ]

        result = processor.extract_quality_data(backend_results, reasoning)

        assert result == {"risk_level": "none", "total_retractions": 0}
        assert len(reasoning) == 0  # No message for zero retractions
