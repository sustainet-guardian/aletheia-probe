# SPDX-License-Identifier: MIT
"""Base utilities for cache components."""

import html
import re
from pathlib import Path


class CacheBase:
    """Base class for cache components with shared utilities."""

    # Common words to ignore for comparison (e.g., "journal of", "the")
    STOP_WORDS = {
        "a",
        "an",
        "and",
        "the",
        "of",
        "in",
        "on",
        "for",
        "with",
        "at",
        "by",
        "to",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "can",
        "will",
        "or",
        "but",
        "not",
        "do",
        "don",
        "s",
        "t",
        "m",
        "ll",
        "d",
        "ve",
        "re",
        "journal",
        "international",
        "conference",
        "proceedings",
    }

    def __init__(self, db_path: Path | None = None):
        """Initialize cache base with database path.

        Args:
            db_path: Path to the SQLite database file. If None, gets from config.
        """
        if db_path is None:
            # Local import to avoid circular dependency (config -> backends -> cache)
            from ..config import get_config_manager
            from .schema import init_database

            db_path_str = get_config_manager().load_config().cache.db_path
            db_path = Path(db_path_str)

            # Ensure parent directory exists
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize database schema
            init_database(db_path)

        self.db_path = db_path

    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize text for robust comparison, removing common words and special characters.

        Args:
            text: The input string (e.g., a journal or conference name).

        Returns:
            A cleaned and normalized string suitable for comparison.
        """
        text = html.unescape(text)
        text = text.lower()
        # Remove common special characters, keeping only alphanumeric and spaces
        text = re.sub(r"[^\w\s]", "", text)
        words = [word for word in text.split() if word not in self.STOP_WORDS]
        return " ".join(words)
