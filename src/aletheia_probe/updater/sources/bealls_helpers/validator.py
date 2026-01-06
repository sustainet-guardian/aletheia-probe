# SPDX-License-Identifier: MIT
"""Validation utilities for Beall's List entries."""

# Validation constants
MIN_JOURNAL_NAME_LENGTH: int = 5
MAX_JOURNAL_NAME_LENGTH: int = 200
MIN_PUBLISHER_NAME_LENGTH: int = 3
MAX_PUBLISHER_NAME_LENGTH: int = 200


class JournalEntryValidator:
    """Validates journal entries from Beall's List."""

    # Navigation and website elements to skip
    NAVIGATION_TERMS: list[str] = [
        "contact",
        "changelog",
        "home",
        "about",
        "privacy",
        "terms",
        "login",
        "register",
        "search",
        "menu",
        "footer",
        "header",
        "skip",
        "navigation",
        "sitemap",
        "update",
        "note",
    ]

    def is_valid_publisher_entry(self, text: str) -> bool:
        """Check if text looks like a valid publisher name.

        Note: Publisher validation is intentionally more permissive than journal
        validation because publisher names have more diverse patterns:
        - Company names (ABC Journals, Academia Publishing)
        - Organization names (Academic and Business Research Institute)
        - Individual names (Abhinav)
        - Branded names (The 5th Publisher)

        However, basic quality checks are applied to filter out navigation
        elements, malformed entries, and concatenated text.

        Args:
            text: Text to validate

        Returns:
            True if text appears to be a valid publisher name

        Raises:
            None
        """
        if not text or len(text.strip()) < MIN_PUBLISHER_NAME_LENGTH:
            return False

        text_lower = text.lower().strip()

        # Reject entries that are too long (likely concatenated text)
        if len(text) > MAX_PUBLISHER_NAME_LENGTH:
            return False

        # Skip navigation and website elements
        if text_lower in self.NAVIGATION_TERMS:
            return False

        # Skip section headers
        if "hijacked" in text_lower or "how to" in text_lower:
            return False

        # Skip very generic single words that aren't publishers
        single_word_generic = ["journals", "publications", "academic", "research"]
        if len(text.split()) == 1 and text_lower in single_word_generic:
            return False

        return True
