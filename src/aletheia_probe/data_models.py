"""Data models and dataclasses for journal assessment tool."""

from dataclasses import dataclass, field
from typing import Any

from .validation import validate_issn


@dataclass
class JournalEntryData:
    """Data for adding a journal entry to the normalized cache."""

    source_name: str
    assessment: str
    journal_name: str
    normalized_name: str
    confidence: float = 1.0
    issn: str | None = None
    eissn: str | None = None
    publisher: str | None = None
    urls: list[str] | None = field(default_factory=list)
    metadata: dict[str, Any] | None = field(default_factory=dict)
    aliases: list[str] | None = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate data after initialization."""
        # Validate required fields
        if not self.source_name or not self.source_name.strip():
            raise ValueError("source_name is required and cannot be empty")
        if not self.assessment or not self.assessment.strip():
            raise ValueError("assessment is required and cannot be empty")
        if not self.journal_name or not self.journal_name.strip():
            raise ValueError("journal_name is required and cannot be empty")
        if not self.normalized_name or not self.normalized_name.strip():
            raise ValueError("normalized_name is required and cannot be empty")

        # Validate confidence
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

        # Clean data
        self.source_name = self.source_name.strip()
        self.assessment = self.assessment.strip()
        self.journal_name = self.journal_name.strip()
        self.normalized_name = self.normalized_name.strip()
        if self.publisher:
            self.publisher = self.publisher.strip()

        # Validate ISSNs if provided
        if self.issn or self.eissn:
            if self.issn and not validate_issn(self.issn):
                raise ValueError(f"Invalid ISSN format: {self.issn}")
            if self.eissn and not validate_issn(self.eissn):
                raise ValueError(f"Invalid e-ISSN format: {self.eissn}")
