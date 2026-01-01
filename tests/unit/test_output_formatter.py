# SPDX-License-Identifier: MIT
"""Tests for the output formatter module."""

from datetime import datetime

import pytest

from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    VenueType,
)
from aletheia_probe.output_formatter import OutputFormatter


@pytest.fixture
def formatter():
    """Create OutputFormatter instance."""
    return OutputFormatter()


@pytest.fixture
def predatory_result_with_details():
    """Create a predatory assessment result with detailed backend data."""
    return AssessmentResult(
        input_query="Test Predatory Journal",
        assessment=AssessmentType.PREDATORY,
        confidence=0.85,
        overall_score=0.85,
        backend_results=[
            BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.90,
                assessment=AssessmentType.PREDATORY,
                data={
                    "metrics": {
                        "years_active": 5,
                        "total_publications": 5000,
                        "publication_rate_per_year": 1000,
                        "citation_ratio": 0.5,
                        "first_year": 2020,
                        "last_year": 2025,
                        "recent_publications": 3000,
                    },
                    "red_flags": [
                        "Publication mill pattern: 1000 papers/year",
                        "Low citation ratio: 0.50 citations per paper",
                    ],
                    "green_flags": [],
                    "publication_type": "journal",
                },
                sources=["https://api.openalex.org"],
                response_time=0.5,
            ),
            BackendResult(
                backend_name="bealls",
                status=BackendStatus.FOUND,
                confidence=0.90,
                assessment=AssessmentType.PREDATORY,
                data={},
                sources=["bealls_list"],
                response_time=0.1,
            ),
            BackendResult(
                backend_name="doaj",
                status=BackendStatus.NOT_FOUND,
                confidence=0.0,
                assessment=None,
                data={},
                sources=["https://doaj.org"],
                response_time=0.2,
            ),
        ],
        metadata=None,
        reasoning=["Found in predatory database", "High publication volume"],
        processing_time=1.5,
        venue_type=VenueType.JOURNAL,
    )


@pytest.fixture
def legitimate_result_with_details():
    """Create a legitimate assessment result with detailed backend data."""
    return AssessmentResult(
        input_query="Nature",
        assessment=AssessmentType.LEGITIMATE,
        confidence=0.92,
        overall_score=0.92,
        backend_results=[
            BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.85,
                assessment=AssessmentType.LEGITIMATE,
                data={
                    "metrics": {
                        "years_active": 150,
                        "total_publications": 100000,
                        "publication_rate_per_year": 666,
                        "citation_ratio": 50.0,
                        "first_year": 1870,
                        "last_year": 2025,
                        "recent_publications": 5000,
                    },
                    "red_flags": [],
                    "green_flags": [
                        "High citation ratio: 50.0 citations per paper",
                        "Well-established journal: 150 years active",
                    ],
                    "publication_type": "journal",
                },
                sources=["https://api.openalex.org"],
                response_time=0.5,
            ),
            BackendResult(
                backend_name="doaj",
                status=BackendStatus.FOUND,
                confidence=0.95,
                assessment=AssessmentType.LEGITIMATE,
                data={},
                sources=["https://doaj.org"],
                response_time=0.2,
            ),
            BackendResult(
                backend_name="scopus",
                status=BackendStatus.FOUND,
                confidence=0.90,
                assessment=AssessmentType.LEGITIMATE,
                data={},
                sources=["scopus"],
                response_time=0.3,
            ),
        ],
        metadata=None,
        reasoning=["High-quality established journal"],
        processing_time=1.0,
        venue_type=VenueType.JOURNAL,
    )


@pytest.fixture
def conflicting_result():
    """Create an assessment result with conflicting backend signals."""
    return AssessmentResult(
        input_query="Conflicting Journal",
        assessment=AssessmentType.PREDATORY,
        confidence=0.65,
        overall_score=0.65,
        backend_results=[
            BackendResult(
                backend_name="openalex_analyzer",
                status=BackendStatus.FOUND,
                confidence=0.70,
                assessment=AssessmentType.PREDATORY,
                data={
                    "metrics": {
                        "years_active": 10,
                        "total_publications": 1000,
                        "publication_rate_per_year": 100,
                        "citation_ratio": 2.0,
                        "first_year": 2015,
                        "last_year": 2025,
                    },
                    "red_flags": ["Some warning"],
                    "green_flags": ["Some positive sign"],
                    "publication_type": "journal",
                },
                sources=["https://api.openalex.org"],
                response_time=0.5,
            ),
            BackendResult(
                backend_name="doaj",
                status=BackendStatus.FOUND,
                confidence=0.95,
                assessment=AssessmentType.LEGITIMATE,
                data={},
                sources=["https://doaj.org"],
                response_time=0.2,
            ),
            BackendResult(
                backend_name="kscien_predatory_conferences",
                status=BackendStatus.FOUND,
                confidence=0.90,
                assessment=AssessmentType.PREDATORY,
                data={},
                sources=["kscien"],
                response_time=0.1,
            ),
        ],
        metadata=None,
        reasoning=["Mixed signals detected"],
        processing_time=1.0,
        venue_type=VenueType.JOURNAL,
    )


class TestOutputFormatter:
    """Test cases for OutputFormatter class."""

    def test_format_text_output_basic_structure(
        self, formatter, predatory_result_with_details
    ):
        """Test that basic output structure is present."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=False
        )

        assert "Journal: Test Predatory Journal" in output
        assert "Assessment: PREDATORY" in output
        assert "Confidence: 0.85" in output
        assert "Overall Score: 0.85" in output
        assert "Processing Time: 1.50s" in output
        assert "Reasoning:" in output
        assert "Recommendation:" in output

    def test_format_text_output_verbose_includes_detailed_analysis(
        self, formatter, predatory_result_with_details
    ):
        """Test that verbose mode includes detailed analysis."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=True
        )

        assert "Detailed Analysis:" in output
        assert "Publication Pattern (OpenAlex):" in output
        assert "Quality Indicators:" in output
        assert "List Presence:" in output
        assert "Backend Results" in output

    def test_format_text_output_non_verbose_no_detailed_analysis(
        self, formatter, predatory_result_with_details
    ):
        """Test that non-verbose mode excludes detailed analysis."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=False
        )

        assert "Detailed Analysis:" not in output
        assert "Publication Pattern" not in output
        assert "Backend Results" not in output

    def test_format_openalex_analysis_displays_metrics(
        self, formatter, predatory_result_with_details
    ):
        """Test that OpenAlex metrics are properly formatted."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=True
        )

        assert "Years active: 5 years (2020-2025)" in output
        assert "Total publications: 5,000 papers" in output
        assert "Publication rate: 1000 papers/year" in output
        # The publication rate line doesn't include the warning because it's already in red_flags
        assert "Citation ratio: 0.5 citations/paper" in output
        assert "[⚠️ Very low]" in output

    def test_format_quality_indicators_red_flags(
        self, formatter, predatory_result_with_details
    ):
        """Test that red flags are properly displayed."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=True
        )

        assert "⚠️  Red Flags (2):" in output
        assert "Publication mill pattern: 1000 papers/year" in output
        assert "Low citation ratio: 0.50 citations per paper" in output

    def test_format_quality_indicators_green_flags(
        self, formatter, legitimate_result_with_details
    ):
        """Test that green flags are properly displayed."""
        output = formatter.format_text_output(
            legitimate_result_with_details, "journal", verbose=True
        )

        assert "✓ Green Flags (2):" in output
        assert "High citation ratio: 50.0 citations per paper" in output
        assert "Well-established journal: 150 years active" in output

    def test_format_list_presence_shows_found_databases(
        self, formatter, predatory_result_with_details
    ):
        """Test that list presence section shows database results."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=True
        )

        assert "List Presence:" in output
        assert "Beall's List: Found" in output
        assert "DOAJ): Not found" in output

    def test_conflicting_signals_detection(self, formatter, conflicting_result):
        """Test that conflicting signals are detected and displayed."""
        output = formatter.format_text_output(
            conflicting_result, "journal", verbose=True
        )

        assert "⚠️  CONFLICTING SIGNALS:" in output
        assert "2 backend(s) report predatory" in output
        assert "1 report legitimate" in output

    def test_no_conflicting_signals_when_unanimous(
        self, formatter, legitimate_result_with_details
    ):
        """Test that no conflict warning when all backends agree."""
        output = formatter.format_text_output(
            legitimate_result_with_details, "journal", verbose=True
        )

        assert "CONFLICTING SIGNALS" not in output

    def test_recommendation_predatory_high_confidence(self, formatter):
        """Test recommendation for high-confidence predatory assessment."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.PREDATORY,
            confidence=0.90,
            overall_score=0.90,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=False)

        assert (
            "🚫 AVOID - Strong evidence of predatory characteristics detected" in output
        )

    def test_recommendation_predatory_medium_confidence(self, formatter):
        """Test recommendation for medium-confidence predatory assessment."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.PREDATORY,
            confidence=0.65,
            overall_score=0.65,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=False)

        assert (
            "⚠️  AVOID - Multiple predatory indicators present, proceed with caution"
            in output
        )

    def test_recommendation_legitimate_high_confidence(self, formatter):
        """Test recommendation for high-confidence legitimate assessment."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.88,
            overall_score=0.88,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=False)

        assert (
            "✓ ACCEPTABLE - Strong evidence of legitimacy, appears trustworthy"
            in output
        )

    def test_recommendation_suspicious(self, formatter):
        """Test recommendation for suspicious assessment."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.SUSPICIOUS,
            confidence=0.50,
            overall_score=0.50,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=False)

        assert (
            "⚠️  INVESTIGATE - Mixed signals detected, requires careful evaluation"
            in output
        )

    def test_recommendation_insufficient_data(self, formatter):
        """Test recommendation for insufficient data."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.UNKNOWN,
            confidence=0.20,
            overall_score=0.00,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=False)

        assert (
            "ℹ️  INSUFFICIENT DATA - Unable to make definitive assessment, research required"
            in output
        )

    def test_conference_type_label(self, formatter):
        """Test that conference type uses correct label."""
        result = AssessmentResult(
            input_query="Test Conference",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.80,
            overall_score=0.80,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "conference", verbose=False)

        assert "Conference: Test Conference" in output

    def test_acronym_expansion_note(self, formatter):
        """Test that acronym expansion note is displayed."""
        result = AssessmentResult(
            input_query="Test Conference",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.80,
            overall_score=0.80,
            backend_results=[],
            reasoning=[],
            processing_time=1.0,
            acronym_expansion_used=True,
            acronym_expanded_from="TC",
        )

        output = formatter.format_text_output(result, "conference", verbose=False)

        assert "Expanded acronym 'TC' using cached mapping" in output

    def test_backend_results_formatting(self, formatter, predatory_result_with_details):
        """Test that backend results are properly formatted."""
        output = formatter.format_text_output(
            predatory_result_with_details, "journal", verbose=True
        )

        assert "Backend Results (3):" in output
        assert "✓ openalex_analyzer: found" in output
        assert "predatory (confidence: 0.90)" in output
        assert "✓ bealls: found" in output
        assert "✗ doaj: not_found" in output

    def test_find_backend_result(self, formatter, predatory_result_with_details):
        """Test finding specific backend results."""
        backend = formatter._find_backend_result(
            predatory_result_with_details, "openalex_analyzer"
        )

        assert backend is not None
        assert backend.backend_name == "openalex_analyzer"
        assert backend.status == BackendStatus.FOUND

    def test_find_backend_result_not_found(
        self, formatter, predatory_result_with_details
    ):
        """Test finding non-existent backend returns None."""
        backend = formatter._find_backend_result(
            predatory_result_with_details, "nonexistent_backend"
        )

        assert backend is None

    def test_check_conflicting_signals_with_conflict(
        self, formatter, conflicting_result
    ):
        """Test detecting conflicting signals."""
        conflict_msg = formatter._check_conflicting_signals(conflicting_result)

        assert conflict_msg is not None
        assert "CONFLICTING SIGNALS" in conflict_msg
        assert "2 backend(s) report predatory" in conflict_msg
        assert "1 report legitimate" in conflict_msg

    def test_check_conflicting_signals_no_conflict(
        self, formatter, legitimate_result_with_details
    ):
        """Test no conflict message when backends agree."""
        conflict_msg = formatter._check_conflicting_signals(
            legitimate_result_with_details
        )

        assert conflict_msg is None

    def test_openalex_analysis_with_conference_type(self, formatter):
        """Test that conference type is displayed in OpenAlex analysis."""
        result = AssessmentResult(
            input_query="Test Conference",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.80,
            overall_score=0.80,
            backend_results=[
                BackendResult(
                    backend_name="openalex_analyzer",
                    status=BackendStatus.FOUND,
                    confidence=0.80,
                    assessment=AssessmentType.LEGITIMATE,
                    data={
                        "metrics": {
                            "years_active": 10,
                            "total_publications": 500,
                            "publication_rate_per_year": 50,
                            "citation_ratio": 10.0,
                        },
                        "red_flags": [],
                        "green_flags": [],
                        "publication_type": "conference",
                    },
                    sources=["https://api.openalex.org"],
                    response_time=0.5,
                )
            ],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "conference", verbose=True)

        assert "Type: Conference proceedings" in output

    def test_openalex_analysis_without_metrics(self, formatter):
        """Test OpenAlex formatting when metrics are missing."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.UNKNOWN,
            confidence=0.20,
            overall_score=0.00,
            backend_results=[
                BackendResult(
                    backend_name="openalex_analyzer",
                    status=BackendStatus.FOUND,
                    confidence=0.50,
                    assessment=None,
                    data={},  # No metrics
                    sources=["https://api.openalex.org"],
                    response_time=0.5,
                )
            ],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=True)

        # Should not crash, and should show detailed analysis section
        assert "Detailed Analysis:" in output
        # But won't have publication pattern details
        assert "Years active:" not in output

    def test_quality_indicators_no_flags(self, formatter):
        """Test quality indicators section when no flags are present."""
        result = AssessmentResult(
            input_query="Test",
            assessment=AssessmentType.UNKNOWN,
            confidence=0.50,
            overall_score=0.50,
            backend_results=[
                BackendResult(
                    backend_name="openalex_analyzer",
                    status=BackendStatus.FOUND,
                    confidence=0.50,
                    assessment=None,
                    data={
                        "metrics": {"years_active": 5, "total_publications": 100},
                        "red_flags": [],
                        "green_flags": [],
                        "publication_type": "journal",
                    },
                    sources=["https://api.openalex.org"],
                    response_time=0.5,
                )
            ],
            reasoning=[],
            processing_time=1.0,
        )

        output = formatter.format_text_output(result, "journal", verbose=True)

        assert "⚠️  Red Flags: None detected" in output
        assert "✓ Green Flags: None detected" in output

    def test_recommendation_with_conflicting_signals_note(
        self, formatter, conflicting_result
    ):
        """Test that recommendation includes note about conflicting signals."""
        output = formatter.format_text_output(
            conflicting_result, "journal", verbose=False
        )

        assert "Recommendation:" in output
        assert (
            "Note: Despite some positive indicators, predatory patterns dominate the assessment"
            in output
        )

    def test_list_presence_multiple_databases(
        self, formatter, legitimate_result_with_details
    ):
        """Test list presence shows multiple database results."""
        output = formatter.format_text_output(
            legitimate_result_with_details, "journal", verbose=True
        )

        assert "List Presence:" in output
        assert "DOAJ): Found (legitimate" in output
        assert "Scopus: Found (legitimate" in output
        # Only backends that are in the backend_results are shown in list presence

    def test_json_output_unchanged(self, formatter, predatory_result_with_details):
        """Test that JSON output format is not affected by formatter."""
        # The formatter doesn't handle JSON output, so we just verify it exists
        # This is tested in the CLI layer, but we can verify the model serialization
        json_data = predatory_result_with_details.model_dump()

        assert "input_query" in json_data
        assert "assessment" in json_data
        assert "backend_results" in json_data
        assert json_data["assessment"] == AssessmentType.PREDATORY
