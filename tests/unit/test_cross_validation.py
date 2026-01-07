# SPDX-License-Identifier: MIT
"""Unit tests for cross-validation functionality."""

from unittest.mock import Mock

import pytest

from aletheia_probe.cross_validation import (
    CrossValidationCapable,
    CrossValidationRegistry,
    OpenAlexCrossRefValidator,
    get_cross_validation_registry,
)
from aletheia_probe.enums import AssessmentType
from aletheia_probe.fallback_chain import QueryFallbackChain
from aletheia_probe.models import BackendResult, BackendStatus


class TestCrossValidationRegistry:
    """Tests for the CrossValidationRegistry class."""

    def test_registry_initialization(self):
        """Test that registry is initialized with default validators."""
        registry = CrossValidationRegistry()

        # Check that OpenAlex-CrossRef validator is registered
        validator = registry.create_validator("openalex_analyzer", "crossref_analyzer")
        assert isinstance(validator, OpenAlexCrossRefValidator)

        # Check that it's order-independent
        validator2 = registry.create_validator("crossref_analyzer", "openalex_analyzer")
        assert isinstance(validator2, OpenAlexCrossRefValidator)

    def test_protocol_methods_are_called(self):
        """Test that protocol methods are actually called during cross-validation."""
        registry = CrossValidationRegistry()

        # Create a mock validator that tracks method calls
        class MockValidator:
            def __init__(self):
                self.validate_called = False
                self.supported_backend_pair_accessed = False

            def validate(self, result1, result2):
                self.validate_called = True
                return {"test": "result"}

            @property
            def supported_backend_pair(self):
                self.supported_backend_pair_accessed = True
                return ("backend1", "backend2")

        mock_validator = MockValidator()
        registry.register_factory("backend1", "backend2", lambda: mock_validator)

        # Test that supported_backend_pair is accessed when checking protocol
        validator = registry.create_validator("backend1", "backend2")
        assert isinstance(validator, MockValidator)

        # Test that validate is called through validate_pair
        result1 = Mock(spec=BackendResult)
        result2 = Mock(spec=BackendResult)
        registry.validate_pair("backend1", result1, "backend2", result2)

        # Verify methods were called
        assert mock_validator.validate_called, (
            "Protocol validate() method was not called"
        )

    def test_register_custom_validator(self):
        """Test registering a custom validator."""
        registry = CrossValidationRegistry()

        class CustomValidator:
            def validate(self, result1, result2):
                return {"test": "data"}

            @property
            def supported_backend_pair(self):
                return ("backend1", "backend2")

        registry.register_factory("backend1", "backend2", lambda: CustomValidator())

        validator = registry.create_validator("backend1", "backend2")
        assert isinstance(validator, CustomValidator)

    def test_get_validator_nonexistent_pair(self):
        """Test getting validator for non-existent pair returns None."""
        registry = CrossValidationRegistry()

        validator = registry.create_validator("nonexistent1", "nonexistent2")
        assert validator is None

    def test_get_registered_pairs(self):
        """Test getting list of registered pairs."""
        registry = CrossValidationRegistry()

        pairs = registry.get_registered_pairs()
        assert ("crossref_analyzer", "openalex_analyzer") in pairs or (
            "openalex_analyzer",
            "crossref_analyzer",
        ) in pairs

    def test_validate_pair_success(self):
        """Test validating a pair of results."""
        registry = CrossValidationRegistry()

        # Create mock results
        result1 = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="openalex_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "openalex_data": {
                    "publisher": "Test Publisher",
                    "total_publications": 100,
                }
            },
            sources=["https://api.openalex.org"],
            error_message=None,
            response_time=1.0,
            cached=False,
        )

        result2 = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="crossref_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.7,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "crossref_data": {
                    "publisher": "Test Publisher",
                    "counts": {"total-dois": 90},
                }
            },
            sources=["https://api.crossref.org"],
            error_message=None,
            response_time=1.2,
            cached=False,
        )

        validation_result = registry.validate_pair(
            "openalex_analyzer", result1, "crossref_analyzer", result2
        )

        assert validation_result is not None
        assert "confidence_adjustment" in validation_result
        assert "consistency_checks" in validation_result
        assert "reasoning" in validation_result

    def test_validate_pair_nonexistent_validator(self):
        """Test validating pair with no registered validator returns None."""
        registry = CrossValidationRegistry()

        result1 = Mock()
        result2 = Mock()

        validation_result = registry.validate_pair(
            "nonexistent1", result1, "nonexistent2", result2
        )

        assert validation_result is None


class TestOpenAlexCrossRefValidator:
    """Tests for the OpenAlexCrossRefValidator class."""

    def test_validator_agreement_scenario(self):
        """Test validator with agreeing backends."""
        validator = OpenAlexCrossRefValidator()

        # Create results that agree
        openalex_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="openalex_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "openalex_data": {
                    "publisher": "Academic Press",
                    "total_publications": 100,
                },
                "analysis": {
                    "red_flags": [],
                    "green_flags": ["High citation ratio"],
                    "reasoning": ["Good metrics"],
                },
            },
            sources=["https://api.openalex.org"],
            error_message=None,
            response_time=1.0,
            cached=False,
        )

        crossref_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="crossref_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.7,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "crossref_data": {
                    "publisher": "Academic Press",
                    "counts": {"total-dois": 95},
                },
                "analysis": {
                    "red_flags": [],
                    "green_flags": ["Good ORCID adoption"],
                    "reasoning": ["Good metadata"],
                },
            },
            sources=["https://api.crossref.org"],
            error_message=None,
            response_time=1.2,
            cached=False,
        )

        result = validator.validate(openalex_result, crossref_result)

        assert result["agreement"] is True
        assert result["confidence_adjustment"] > 0  # Agreement bonus
        assert len(result["consistency_checks"]) > 0
        assert "Publisher names consistent" in str(result["consistency_checks"])

    def test_validator_disagreement_scenario(self):
        """Test validator with disagreeing backends."""
        validator = OpenAlexCrossRefValidator()

        # Create results that disagree
        openalex_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="openalex_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "openalex_data": {
                    "publisher": "Academic Press",
                    "total_publications": 100,
                },
                "analysis": {"red_flags": [], "green_flags": [], "reasoning": []},
            },
            sources=["https://api.openalex.org"],
            error_message=None,
            response_time=1.0,
            cached=False,
        )

        crossref_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="crossref_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.5,
            assessment=AssessmentType.PREDATORY,
            data={
                "crossref_data": {
                    "publisher": "Academic Press",
                    "counts": {"total-dois": 95},
                },
                "analysis": {
                    "red_flags": ["Poor ORCID adoption"],
                    "green_flags": [],
                    "reasoning": [],
                },
            },
            sources=["https://api.crossref.org"],
            error_message=None,
            response_time=1.2,
            cached=False,
        )

        result = validator.validate(openalex_result, crossref_result)

        assert result["agreement"] is False
        assert result["confidence_adjustment"] < 0  # Disagreement penalty
        assert "Backend disagreement" in str(result["reasoning"])

    def test_validator_single_backend_scenario(self):
        """Test validator with only one backend having results."""
        validator = OpenAlexCrossRefValidator()

        openalex_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="openalex_analyzer",
            status=BackendStatus.FOUND,
            confidence=0.8,
            assessment=AssessmentType.LEGITIMATE,
            data={
                "openalex_data": {"publisher": "Academic Press"},
                "analysis": {"red_flags": [], "green_flags": [], "reasoning": []},
            },
            sources=["https://api.openalex.org"],
            error_message=None,
            response_time=1.0,
            cached=False,
        )

        crossref_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="crossref_analyzer",
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={},
            sources=["https://api.crossref.org"],
            error_message="Not found",
            response_time=1.2,
            cached=False,
        )

        result = validator.validate(openalex_result, crossref_result)

        assert result["agreement"] is False
        assert result["confidence_adjustment"] < 0  # Single source penalty
        assert "Only found in OpenAlex" in str(result["consistency_checks"])

    def test_validator_no_results_scenario(self):
        """Test validator with no backends having results."""
        validator = OpenAlexCrossRefValidator()

        openalex_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="openalex_analyzer",
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={},
            sources=["https://api.openalex.org"],
            error_message="Not found",
            response_time=1.0,
            cached=False,
        )

        crossref_result = BackendResult(
            fallback_chain=QueryFallbackChain([]),
            backend_name="crossref_analyzer",
            status=BackendStatus.NOT_FOUND,
            confidence=0.0,
            assessment=None,
            data={},
            sources=["https://api.crossref.org"],
            error_message="Not found",
            response_time=1.2,
            cached=False,
        )

        result = validator.validate(openalex_result, crossref_result)

        assert result["agreement"] is False
        assert result["confidence_adjustment"] == 0.0
        assert "not found in either OpenAlex or CrossRef" in str(result["reasoning"])

    def test_consistency_checks(self):
        """Test specific consistency check scenarios."""
        validator = OpenAlexCrossRefValidator()

        # Test publisher name mismatch
        openalex_data = {"publisher": "Publisher A", "total_publications": 100}
        crossref_data = {"publisher": "Publisher B", "counts": {"total-dois": 50}}

        checks = validator._perform_consistency_checks(openalex_data, crossref_data)

        assert any("Publisher name mismatch" in check for check in checks)
        assert any(
            "volume difference" in check.lower()
            or "volume discrepancy" in check.lower()
            for check in checks
        )
