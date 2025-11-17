"""Tests for core data models."""

from datetime import datetime

import pytest

from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    ConfigBackend,
    JournalMetadata,
    QueryInput,
)


class TestQueryInput:
    """Tests for QueryInput model."""

    def test_create_basic_query_input(self):
        """Test creating a basic QueryInput."""
        query = QueryInput(raw_input="Test Journal")
        assert query.raw_input == "Test Journal"
        assert query.normalized_name is None
        assert query.identifiers == {}
        assert query.aliases == []

    def test_create_full_query_input(self):
        """Test creating a QueryInput with all fields."""
        query = QueryInput(
            raw_input="J. Test Sci.",
            normalized_name="Journal of Test Science",
            identifiers={"issn": "1234-5678"},
            aliases=["Test Science Journal"],
        )
        assert query.raw_input == "J. Test Sci."
        assert query.normalized_name == "Journal of Test Science"
        assert query.identifiers["issn"] == "1234-5678"
        assert "Test Science Journal" in query.aliases


class TestBackendResult:
    """Tests for BackendResult model."""

    def test_create_basic_backend_result(self):
        """Test creating a basic BackendResult."""
        result = BackendResult(
            backend_name="test_backend",
            status=BackendStatus.FOUND,
            confidence=0.8,
            response_time=1.5,
        )
        assert result.backend_name == "test_backend"
        assert result.status == BackendStatus.FOUND
        assert result.confidence == 0.8
        assert result.assessment is None
        assert result.response_time == 1.5

    def test_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence
        result = BackendResult(
            backend_name="test",
            status=BackendStatus.FOUND,
            confidence=0.5,
            response_time=1.0,
        )
        assert result.confidence == 0.5

        # Invalid confidence - too high
        with pytest.raises(ValueError):
            BackendResult(
                backend_name="test",
                status=BackendStatus.FOUND,
                confidence=1.5,
                response_time=1.0,
            )

        # Invalid confidence - too low
        with pytest.raises(ValueError):
            BackendResult(
                backend_name="test",
                status=BackendStatus.FOUND,
                confidence=-0.1,
                response_time=1.0,
            )


class TestJournalMetadata:
    """Tests for JournalMetadata model."""

    def test_create_basic_metadata(self):
        """Test creating basic journal metadata."""
        metadata = JournalMetadata(name="Test Journal")
        assert metadata.name == "Test Journal"
        assert metadata.issn is None
        assert metadata.subject_areas == []

    def test_create_full_metadata(self):
        """Test creating full journal metadata."""
        metadata = JournalMetadata(
            name="International Journal of Testing",
            issn="1234-5678",
            eissn="8765-4321",
            publisher="Test Publisher",
            subject_areas=["Computer Science", "Testing"],
            founding_year=2000,
            country="United States",
            language=["English"],
            open_access=True,
            peer_reviewed=True,
        )
        assert metadata.name == "International Journal of Testing"
        assert metadata.issn == "1234-5678"
        assert "Computer Science" in metadata.subject_areas
        assert metadata.open_access is True


class TestAssessmentResult:
    """Tests for AssessmentResult model."""

    def test_create_assessment_result(self):
        """Test creating an assessment result."""
        result = AssessmentResult(
            input_query="Test Journal",
            assessment="legitimate",
            confidence=0.9,
            overall_score=0.85,
            processing_time=2.5,
        )
        assert result.input_query == "Test Journal"
        assert result.assessment == "legitimate"
        assert result.confidence == 0.9
        assert isinstance(result.timestamp, datetime)


class TestConfigBackend:
    """Tests for ConfigBackend model."""

    def test_create_backend_config(self):
        """Test creating backend configuration."""
        config = ConfigBackend(
            name="test_backend", enabled=True, weight=0.8, timeout=15
        )
        assert config.name == "test_backend"
        assert config.enabled is True
        assert config.weight == 0.8
        assert config.timeout == 15
        assert config.rate_limit is None
