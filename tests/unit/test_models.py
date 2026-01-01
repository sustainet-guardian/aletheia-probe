# SPDX-License-Identifier: MIT
"""Tests for core data models."""

from datetime import datetime

import pytest

from aletheia_probe.models import (
    VENUE_TYPE_EMOJI,
    AssessmentResult,
    AssessmentType,
    BackendResult,
    BackendStatus,
    BibtexAssessmentResult,
    BibtexEntry,
    ConfigBackend,
    JournalMetadata,
    QueryInput,
    VenueType,
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
            identifiers={"issn": "1234-5679"},
            aliases=["Test Science Journal"],
        )
        assert query.raw_input == "J. Test Sci."
        assert query.normalized_name == "Journal of Test Science"
        assert query.identifiers["issn"] == "1234-5679"
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
            issn="1234-5679",
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
        assert metadata.issn == "1234-5679"
        assert "Computer Science" in metadata.subject_areas
        assert metadata.open_access is True


class TestAssessmentResult:
    """Tests for AssessmentResult model."""

    def test_create_assessment_result(self):
        """Test creating an assessment result."""
        result = AssessmentResult(
            input_query="Test Journal",
            assessment=AssessmentType.LEGITIMATE,
            confidence=0.9,
            overall_score=0.85,
            processing_time=2.5,
        )
        assert result.input_query == "Test Journal"
        assert result.assessment == AssessmentType.LEGITIMATE
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

    def test_backend_config_with_valid_email(self):
        """Test creating backend configuration with valid email."""
        config = ConfigBackend(
            name="test_backend",
            enabled=True,
            weight=1.0,
            timeout=10,
            email="user@example.com",
        )
        assert config.email == "user@example.com"

    def test_backend_config_with_invalid_email(self):
        """Test creating backend configuration with invalid email."""
        with pytest.raises(ValueError, match="Invalid email format"):
            ConfigBackend(
                name="test_backend",
                enabled=True,
                weight=1.0,
                timeout=10,
                email="invalid-email",
            )

    def test_backend_config_with_none_email(self):
        """Test creating backend configuration with None email."""
        config = ConfigBackend(
            name="test_backend", enabled=True, weight=1.0, timeout=10, email=None
        )
        assert config.email is None


class TestVenueType:
    """Tests for VenueType enum."""

    def test_all_venue_types_exist(self):
        """Test that all expected venue types are defined."""
        assert VenueType.JOURNAL == "journal"
        assert VenueType.CONFERENCE == "conference"
        assert VenueType.WORKSHOP == "workshop"
        assert VenueType.SYMPOSIUM == "symposium"
        assert VenueType.PROCEEDINGS == "proceedings"
        assert VenueType.BOOK == "book"
        assert VenueType.PREPRINT == "preprint"
        assert VenueType.UNKNOWN == "unknown"

    def test_venue_type_by_value(self):
        """Test accessing VenueType by string value."""
        assert VenueType("journal") == VenueType.JOURNAL
        assert VenueType("conference") == VenueType.CONFERENCE
        assert VenueType("unknown") == VenueType.UNKNOWN

    def test_venue_type_count(self):
        """Test that VenueType has expected number of values."""
        assert len(VenueType) == 8


class TestVenueTypeEmoji:
    """Tests for VENUE_TYPE_EMOJI mapping."""

    def test_all_venue_types_have_emojis(self):
        """Test that all VenueType values have corresponding emojis."""
        for venue_type in VenueType:
            assert venue_type in VENUE_TYPE_EMOJI

    def test_emoji_mapping_completeness(self):
        """Test that emoji mapping has exactly the right number of entries."""
        assert len(VENUE_TYPE_EMOJI) == len(VenueType)

    def test_specific_emoji_mappings(self):
        """Test specific emoji mappings are correct."""
        assert VENUE_TYPE_EMOJI[VenueType.JOURNAL] == "📄"
        assert VENUE_TYPE_EMOJI[VenueType.CONFERENCE] == "🎤"
        assert VENUE_TYPE_EMOJI[VenueType.WORKSHOP] == "🔧"
        assert VENUE_TYPE_EMOJI[VenueType.SYMPOSIUM] == "🎪"
        assert VENUE_TYPE_EMOJI[VenueType.PROCEEDINGS] == "📑"
        assert VENUE_TYPE_EMOJI[VenueType.BOOK] == "📚"
        assert VENUE_TYPE_EMOJI[VenueType.PREPRINT] == "📝"
        assert VENUE_TYPE_EMOJI[VenueType.UNKNOWN] == "❓"


class TestBibtexEntry:
    """Tests for BibtexEntry model."""

    def test_create_minimal_bibtex_entry(self):
        """Test creating a BibtexEntry with only required fields."""
        entry = BibtexEntry(
            key="testkey2024",
            journal_name="Test Journal",
            entry_type="article",
        )
        assert entry.key == "testkey2024"
        assert entry.journal_name == "Test Journal"
        assert entry.entry_type == "article"
        assert entry.venue_type == VenueType.UNKNOWN
        assert entry.title is None
        assert entry.authors is None
        assert entry.year is None
        assert entry.doi is None
        assert entry.isbn is None
        assert entry.issn is None
        assert entry.url is None
        assert entry.publisher is None
        assert entry.booktitle is None
        assert entry.series is None
        assert entry.organization is None
        assert entry.is_retracted is False
        assert entry.retraction_info is None

    def test_create_full_bibtex_entry(self):
        """Test creating a BibtexEntry with all fields."""
        entry = BibtexEntry(
            key="smith2024test",
            journal_name="International Journal of Testing",
            entry_type="article",
            venue_type=VenueType.JOURNAL,
            title="A Test Article",
            authors="Smith, J. and Doe, A.",
            year="2024",
            doi="10.1234/test.2024",
            issn="1234-5679",
            url="https://example.com/article",
            publisher="Test Publisher",
        )
        assert entry.key == "smith2024test"
        assert entry.journal_name == "International Journal of Testing"
        assert entry.entry_type == "article"
        assert entry.venue_type == VenueType.JOURNAL
        assert entry.title == "A Test Article"
        assert entry.authors == "Smith, J. and Doe, A."
        assert entry.year == "2024"
        assert entry.doi == "10.1234/test.2024"
        assert entry.issn == "1234-5679"
        assert entry.url == "https://example.com/article"
        assert entry.publisher == "Test Publisher"

    def test_bibtex_entry_with_conference_fields(self):
        """Test BibtexEntry with conference-specific fields."""
        entry = BibtexEntry(
            key="conf2024",
            journal_name="TestConf 2024",
            entry_type="inproceedings",
            venue_type=VenueType.CONFERENCE,
            booktitle="Proceedings of TestConf 2024",
            series="TestConf Series",
            organization="Test Organization",
        )
        assert entry.venue_type == VenueType.CONFERENCE
        assert entry.booktitle == "Proceedings of TestConf 2024"
        assert entry.series == "TestConf Series"
        assert entry.organization == "Test Organization"

    def test_bibtex_entry_retraction_fields(self):
        """Test BibtexEntry retraction information fields."""
        retraction_details = {
            "retraction_doi": "10.1234/retraction.2024",
            "retraction_date": "2024-05-15",
            "reason": "Data integrity issues",
        }
        entry = BibtexEntry(
            key="retracted2024",
            journal_name="Test Journal",
            entry_type="article",
            is_retracted=True,
            retraction_info=retraction_details,
        )
        assert entry.is_retracted is True
        assert entry.retraction_info == retraction_details
        assert entry.retraction_info["reason"] == "Data integrity issues"


class TestBibtexAssessmentResult:
    """Tests for BibtexAssessmentResult model."""

    def test_create_minimal_bibtex_assessment_result(self):
        """Test creating a BibtexAssessmentResult with minimal fields."""
        result = BibtexAssessmentResult(
            file_path="/path/to/test.bib",
            total_entries=10,
            entries_with_journals=8,
            processing_time=5.2,
        )
        assert result.file_path == "/path/to/test.bib"
        assert result.total_entries == 10
        assert result.entries_with_journals == 8
        assert result.processing_time == 5.2
        assert result.preprint_entries_count == 0
        assert result.skipped_entries_count == 0
        assert result.assessment_results == []
        assert result.predatory_count == 0
        assert result.legitimate_count == 0
        assert result.insufficient_data_count == 0
        assert result.suspicious_count == 0
        assert result.conference_entries == 0
        assert result.conference_predatory == 0
        assert result.conference_legitimate == 0
        assert result.conference_suspicious == 0
        assert result.journal_entries == 0
        assert result.journal_predatory == 0
        assert result.journal_legitimate == 0
        assert result.journal_suspicious == 0
        assert result.has_predatory_journals is False
        assert result.venue_type_counts == {}
        assert result.retracted_articles_count == 0
        assert result.articles_checked_for_retraction == 0

    def test_create_full_bibtex_assessment_result(self):
        """Test creating a BibtexAssessmentResult with all counters."""
        result = BibtexAssessmentResult(
            file_path="/path/to/comprehensive.bib",
            total_entries=50,
            entries_with_journals=45,
            preprint_entries_count=3,
            skipped_entries_count=2,
            predatory_count=5,
            legitimate_count=30,
            insufficient_data_count=8,
            suspicious_count=2,
            conference_entries=20,
            conference_predatory=2,
            conference_legitimate=15,
            conference_suspicious=1,
            journal_entries=25,
            journal_predatory=3,
            journal_legitimate=15,
            journal_suspicious=1,
            has_predatory_journals=True,
            venue_type_counts={
                VenueType.JOURNAL: 25,
                VenueType.CONFERENCE: 20,
                VenueType.PREPRINT: 3,
                VenueType.UNKNOWN: 2,
            },
            retracted_articles_count=2,
            articles_checked_for_retraction=40,
            processing_time=120.5,
        )
        assert result.total_entries == 50
        assert result.predatory_count == 5
        assert result.legitimate_count == 30
        assert result.conference_entries == 20
        assert result.journal_entries == 25
        assert result.has_predatory_journals is True
        assert result.venue_type_counts[VenueType.JOURNAL] == 25
        assert result.venue_type_counts[VenueType.CONFERENCE] == 20
        assert result.retracted_articles_count == 2
        assert result.articles_checked_for_retraction == 40

    def test_bibtex_assessment_result_empty_assessment_list(self):
        """Test BibtexAssessmentResult with empty assessment list."""
        result = BibtexAssessmentResult(
            file_path="/path/to/empty.bib",
            total_entries=0,
            entries_with_journals=0,
            processing_time=0.1,
        )
        assert result.assessment_results == []
        assert len(result.assessment_results) == 0
