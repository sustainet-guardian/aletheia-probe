# SPDX-License-Identifier: MIT
"""Utility functions for data updating and processing."""

import html
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar


# Generic type for deduplication
T = TypeVar("T")


def normalize_journal_name(name: str) -> str:
    """
    Normalize journal name for comparison across different sources.

    This provides normalization that removes URLs, parenthetical content,
    special characters, and converts to lowercase for matching journal names
    that may appear with slight variations across different data sources.

    Args:
        name: Raw journal name

    Returns:
        Normalized journal name (lowercase, cleaned, URLs/metadata removed)
    """
    if not name:
        return ""

    # Unescape HTML entities first
    normalized = html.unescape(name)

    # Remove URLs and domain names (common in some sources)
    # Match patterns like "journal.com", "w.journal.org/", etc.
    normalized = re.sub(
        r"\s*-\s*[a-zA-Z0-9.-]+\.(org|com|net|edu|info|co|uk|de|fr)[/\w.-]*",
        "",
        normalized,
    )
    normalized = re.sub(
        r"\s+[wW]+\.[a-zA-Z0-9.-]+\.(org|com|net|edu)[/\w.-]*", "", normalized
    )

    # Remove content in parentheses and brackets (abbreviations, notes, publisher info)
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"\[[^\]]*\]", "", normalized)

    # Convert to lowercase
    normalized = normalized.lower()

    # Remove all special characters (keep only alphanumeric and whitespace)
    normalized = re.sub(r"[^\w\s]", " ", normalized)

    # Normalize whitespace
    normalized = re.sub(r"\s+", " ", normalized.strip())

    return normalized


def clean_publisher_name(name: str | None) -> str:
    """Clean and normalize publisher name."""
    if not name:
        return ""

    # Clean HTML entities and extra whitespace
    cleaned = html.unescape(name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Remove common prefixes/suffixes
    cleaned = re.sub(r"^(The |A |An )", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(\s+Inc\.?|\s+LLC|\s+Ltd\.?|\s+Co\.?|\s+GmbH)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


def parse_date_string(date_str: str | None) -> datetime | None:
    """Parse various date formats into datetime objects."""
    if not date_str:
        return None

    # Common date formats to try
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%B %d, %Y",  # December 1, 2023
        "%Y",
        "%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def extract_year_from_text(text: str) -> int | None:
    """Extract year from text."""
    if not text:
        return None

    # Look for 4-digit year between 1900-2100
    year_pattern = r"\b(19|20)\d{2}\b"
    match = re.search(year_pattern, text)

    if match:
        year = int(match.group())
        if 1900 <= year <= 2100:
            return year

    return None


def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""

    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    cleaned = html.unescape(cleaned)

    # Clean up whitespace
    cleaned = re.sub(r"\s+", " ", cleaned.strip())

    return cleaned


def deduplicate_entries(
    entries: list[T],
    key_func: Callable[[T], str],
) -> list[T]:
    """
    Deduplicate entries based on a key function.

    Preserves order, keeping first occurrence of each unique key.

    Args:
        entries: List of entries to deduplicate
        key_func: Function to extract comparison key from entry

    Returns:
        Deduplicated list

    Examples:
        >>> entries = [{"name": "A"}, {"name": "B"}, {"name": "A"}]
        >>> deduplicate_entries(entries, lambda x: x["name"])
        [{"name": "A"}, {"name": "B"}]
    """
    seen = set()
    result = []

    for entry in entries:
        key = key_func(entry).lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(entry)

    return result


def deduplicate_journals(journals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove duplicate journals based on normalized names.

    Args:
        journals: List of journal dictionaries

    Returns:
        Deduplicated list of journals
    """

    def get_journal_key(journal: dict[str, Any]) -> str:
        # Use normalized_name if available, otherwise fall back to journal_name
        normalized_name: str = str(journal.get("normalized_name", ""))
        if not normalized_name and "journal_name" in journal:
            normalized_name = str(journal["journal_name"])
        return normalized_name

    return deduplicate_entries(journals, get_journal_key)


def calculate_risk_level(
    total_retractions: int, total_publications: int | None = None
) -> str:
    """
    Calculate risk level based on retraction counts/rates.

    Wrapper function using centralized risk calculator.

    Args:
        total_retractions: Total number of retractions
        total_publications: Total number of publications (optional)

    Returns:
        Risk level string
    """
    # Import here to avoid circular dependency
    from ..risk_calculator import calculate_retraction_risk_level

    # Pass 0 for recent_retractions since this standalone function doesn't track that
    return calculate_retraction_risk_level(
        total_retractions, 0, total_publications, None
    )
