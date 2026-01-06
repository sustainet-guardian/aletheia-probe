# SPDX-License-Identifier: MIT
"""Utility functions for data updating and processing."""

from collections.abc import Callable
from typing import Any, TypeVar


# Generic type for deduplication
T = TypeVar("T")


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
