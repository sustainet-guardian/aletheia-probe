# SPDX-License-Identifier: MIT
"""Core data models for the journal assessment tool."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .validation import validate_email as _validate_email


class VenueType(str, Enum):
    """Types of academic venues for publication classification."""

    JOURNAL = "journal"
    CONFERENCE = "conference"
    WORKSHOP = "workshop"
    SYMPOSIUM = "symposium"
    PROCEEDINGS = "proceedings"
    BOOK = "book"
    PREPRINT = "preprint"
    UNKNOWN = "unknown"


# Centralized venue type emoji mapping
VENUE_TYPE_EMOJI: dict[VenueType, str] = {
    VenueType.JOURNAL: "📄",
    VenueType.CONFERENCE: "🎤",
    VenueType.WORKSHOP: "🔧",
    VenueType.SYMPOSIUM: "🎪",
    VenueType.PROCEEDINGS: "📑",
    VenueType.BOOK: "📚",
    VenueType.PREPRINT: "📝",
    VenueType.UNKNOWN: "❓",
}


class BackendStatus(Enum):
    """Status of a backend query result."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


class QueryInput(BaseModel):
    """Input query data for journal assessment."""

    raw_input: str = Field(..., description="Original user input")
    normalized_name: str | None = Field(None, description="Normalized journal name")
    identifiers: dict[str, str] = Field(
        default_factory=dict, description="ISSN, DOI, etc."
    )
    aliases: list[str] = Field(default_factory=list, description="Alternative names")
    acronym_expanded_from: str | None = Field(
        None, description="Original acronym if expansion was applied"
    )
    venue_type: VenueType = Field(
        VenueType.UNKNOWN, description="Detected venue type (journal, conference, etc.)"
    )
    extracted_acronym_mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Acronym to full name mappings extracted during normalization",
    )


class BackendResult(BaseModel):
    """Result from a single backend query."""

    backend_name: str = Field(..., description="Name of the backend")
    status: BackendStatus = Field(..., description="Query result status")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0"
    )
    assessment: str | None = Field(
        None, description="predatory, legitimate, suspicious, or unknown"
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Backend-specific raw data"
    )
    sources: list[str] = Field(
        default_factory=list, description="URLs, list names, etc."
    )
    error_message: str | None = Field(
        None, description="Error details if status is ERROR"
    )
    response_time: float = Field(..., description="Query response time in seconds")
    cached: bool = Field(False, description="Whether result was retrieved from cache")
    execution_time_ms: float | None = Field(
        None, description="Backend execution time in milliseconds"
    )
    evidence_type: str | None = Field(
        None,
        description="Type of evidence: predatory_list, legitimate_list, or heuristic",
    )


class JournalMetadata(BaseModel):
    """Metadata about a journal."""

    name: str = Field(..., description="Journal name")
    issn: str | None = Field(None, description="Print ISSN")
    eissn: str | None = Field(None, description="Electronic ISSN")
    publisher: str | None = Field(None, description="Publisher name")
    subject_areas: list[str] = Field(default_factory=list, description="Subject areas")
    founding_year: int | None = Field(None, description="Year journal was founded")
    country: str | None = Field(None, description="Country of publication")
    language: list[str] = Field(
        default_factory=list, description="Publication languages"
    )
    open_access: bool | None = Field(None, description="Is open access journal")
    peer_reviewed: bool | None = Field(None, description="Is peer reviewed")


class AssessmentResult(BaseModel):
    """Final assessment result for a journal query."""

    input_query: str = Field(..., description="Original query string")
    assessment: str = Field(
        ..., description="predatory, legitimate, suspicious, or insufficient_data"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall confidence score"
    )
    overall_score: float = Field(..., description="Aggregated assessment score")
    backend_results: list[BackendResult] = Field(
        default_factory=list, description="Individual backend results"
    )
    metadata: JournalMetadata | None = Field(
        None, description="Journal metadata if available"
    )
    reasoning: list[str] = Field(
        default_factory=list, description="Human-readable explanations"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Assessment timestamp"
    )
    processing_time: float = Field(..., description="Total processing time in seconds")
    acronym_expanded_from: str | None = Field(
        None, description="Original acronym if expansion was applied during assessment"
    )
    acronym_expansion_used: bool = Field(
        False, description="Whether acronym expansion was used to get results"
    )
    venue_type: VenueType = Field(
        VenueType.UNKNOWN, description="Detected venue type (journal, conference, etc.)"
    )


class ConfigBackend(BaseModel):
    """Configuration for a backend."""

    name: str = Field(..., description="Backend name")
    enabled: bool = Field(True, description="Is backend enabled")
    weight: float = Field(1.0, ge=0.0, description="Weight in final assessment")
    timeout: int = Field(10, gt=0, description="Timeout in seconds")
    rate_limit: int | None = Field(None, description="Rate limit requests per minute")
    email: str | None = Field(
        None, description="Email address for API identification (Crossref, OpenAlex)"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Backend-specific settings"
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        """Validate email format."""
        if v is None:
            return v

        return _validate_email(v)


class BibtexEntry(BaseModel):
    """Represents a journal or conference entry extracted from a BibTeX file."""

    key: str = Field(..., description="BibTeX entry key")
    journal_name: str = Field(..., description="Extracted journal or conference name")
    entry_type: str = Field(
        ..., description="BibTeX entry type (article, inproceedings, etc.)"
    )
    venue_type: VenueType = Field(
        VenueType.UNKNOWN, description="Detected venue type (journal, conference, etc.)"
    )
    title: str | None = Field(None, description="Paper/article title")
    authors: str | None = Field(None, description="Authors")
    year: str | None = Field(None, description="Publication year")
    doi: str | None = Field(None, description="DOI")
    isbn: str | None = Field(None, description="ISBN")
    issn: str | None = Field(None, description="ISSN")
    url: str | None = Field(None, description="URL")
    publisher: str | None = Field(None, description="Publisher")
    booktitle: str | None = Field(
        None, description="Conference name from booktitle field"
    )
    series: str | None = Field(None, description="Conference series")
    organization: str | None = Field(None, description="Conference organization")
    raw_entry: Any = Field(None, description="Raw BibTeX entry object")
    # Article retraction information
    is_retracted: bool = Field(False, description="Whether the article is retracted")
    retraction_info: dict[str, Any] | None = Field(
        None, description="Retraction details if article is retracted"
    )


class BibtexAssessmentResult(BaseModel):
    """Result of assessing all journals and conferences in a BibTeX file."""

    file_path: str = Field(..., description="Path to the assessed BibTeX file")
    total_entries: int = Field(..., description="Total number of entries processed")
    entries_with_journals: int = Field(
        ..., description="Number of entries with identifiable journals"
    )
    preprint_entries_count: int = Field(
        0,
        description="Number of entries identified as legitimate preprints (arXiv, bioRxiv, SSRN, etc.)",
    )
    skipped_entries_count: int = Field(
        0, description="Number of entries skipped for other reasons"
    )
    assessment_results: list[tuple[BibtexEntry, AssessmentResult]] = Field(
        default_factory=list, description="List of (entry, assessment) pairs"
    )
    predatory_count: int = Field(
        0, description="Number of entries with predatory journals/conferences"
    )
    legitimate_count: int = Field(
        0, description="Number of entries with legitimate journals/conferences"
    )
    insufficient_data_count: int = Field(
        0, description="Number of entries with insufficient data"
    )
    suspicious_count: int = Field(
        0, description="Number of entries with suspicious journals/conferences"
    )
    # Conference-specific counters
    conference_entries: int = Field(
        0,
        description="Number of conference entries (inproceedings, conference, proceedings)",
    )
    conference_predatory: int = Field(0, description="Number of predatory conferences")
    conference_legitimate: int = Field(
        0, description="Number of legitimate conferences"
    )
    conference_suspicious: int = Field(
        0, description="Number of suspicious conferences"
    )
    # Journal-specific counters
    journal_entries: int = Field(
        0, description="Number of journal entries (article, etc.)"
    )
    journal_predatory: int = Field(0, description="Number of predatory journals")
    journal_legitimate: int = Field(0, description="Number of legitimate journals")
    journal_suspicious: int = Field(0, description="Number of suspicious journals")
    has_predatory_journals: bool = Field(
        False, description="Whether any predatory journals/conferences were found"
    )
    # Venue type counters
    venue_type_counts: dict[VenueType, int] = Field(
        default_factory=dict, description="Count of entries by venue type"
    )
    # Article retraction counters
    retracted_articles_count: int = Field(
        0, description="Number of retracted articles found"
    )
    articles_checked_for_retraction: int = Field(
        0, description="Number of articles checked for retraction (had DOIs)"
    )
    processing_time: float = Field(..., description="Total processing time in seconds")
