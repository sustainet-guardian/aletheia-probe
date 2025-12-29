# SPDX-License-Identifier: MIT
"""Data models and dataclasses for journal assessment tool."""

from typing import Any, TypedDict

from pydantic import BaseModel, Field, field_validator
from typing_extensions import NotRequired

from .enums import AssessmentType
from .validation import validate_issn


def strip_whitespace_validator(v: str) -> str:
    """Strip whitespace from string fields."""
    return v.strip()


def strip_publisher_validator(v: str | None) -> str | None:
    """Strip whitespace from publisher field."""
    return v.strip() if v else v


def validate_issn_format_validator(v: str | None) -> str | None:
    """Validate ISSN format."""
    if v and not validate_issn(v):
        raise ValueError(f"Invalid ISSN format: {v}")
    return v


class JournalDataDict(TypedDict):
    """TypedDict for journal data structure used in cache synchronization.

    This defines the structure of journal dictionaries passed to AsyncDBWriter
    and other cache synchronization operations. Using TypedDict provides type
    safety and clear documentation without runtime overhead.
    """

    journal_name: str
    normalized_name: str
    issn: NotRequired[str | None]
    eissn: NotRequired[str | None]
    publisher: NotRequired[str | None]
    urls: NotRequired[list[str] | str | None]
    metadata: NotRequired[dict[str, Any]]


class JournalData(BaseModel):
    """Journal data structure for cache synchronization and database writing.

    This model represents the minimal journal data structure expected by
    AsyncDBWriter and cache synchronization operations.
    """

    journal_name: str = Field(..., min_length=1, description="Display journal name")
    normalized_name: str = Field(
        ..., min_length=1, description="Normalized journal name for deduplication"
    )
    issn: str | None = Field(None, description="Print ISSN")
    eissn: str | None = Field(None, description="Electronic ISSN")
    publisher: str | None = Field(None, description="Publisher name")
    urls: list[str] | str | None = Field(
        None, description="Journal URLs (list or single URL string)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @field_validator("journal_name", "normalized_name", mode="after")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return strip_whitespace_validator(v)

    @field_validator("publisher", mode="after")
    @classmethod
    def strip_publisher(cls, v: str | None) -> str | None:
        return strip_publisher_validator(v)

    @field_validator("issn", "eissn", mode="after")
    @classmethod
    def validate_issn_format(cls, v: str | None) -> str | None:
        return validate_issn_format_validator(v)


class JournalEntryData(BaseModel):
    """Data for adding a journal entry to the normalized cache."""

    source_name: str = Field(..., min_length=1, description="Data source name")
    assessment: AssessmentType = Field(..., description="Assessment type")
    journal_name: str = Field(..., min_length=1, description="Display journal name")
    normalized_name: str = Field(
        ..., min_length=1, description="Normalized journal name for deduplication"
    )
    confidence: float = Field(
        1.0, ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)"
    )
    issn: str | None = Field(None, description="Print ISSN")
    eissn: str | None = Field(None, description="Electronic ISSN")
    publisher: str | None = Field(None, description="Publisher name")
    urls: list[str] = Field(default_factory=list, description="List of URLs")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    aliases: list[str] = Field(
        default_factory=list, description="List of journal name aliases"
    )

    @field_validator("source_name", "journal_name", "normalized_name", mode="after")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return strip_whitespace_validator(v)

    @field_validator("publisher", mode="after")
    @classmethod
    def strip_publisher(cls, v: str | None) -> str | None:
        return strip_publisher_validator(v)

    @field_validator("issn", "eissn", mode="after")
    @classmethod
    def validate_issn_format(cls, v: str | None) -> str | None:
        return validate_issn_format_validator(v)
