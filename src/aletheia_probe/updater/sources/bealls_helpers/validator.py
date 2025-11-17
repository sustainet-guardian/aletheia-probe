"""Validation utilities for Beall's List entries."""


class JournalEntryValidator:
    """Validates journal entries from Beall's List."""

    def is_valid_journal_entry(self, text: str) -> bool:
        """Check if text looks like a valid journal name.

        Args:
            text: Text to validate

        Returns:
            True if text appears to be a valid journal name
        """
        if not text or len(text.strip()) < 5:
            return False

        text = text.lower().strip()

        # Skip navigation and website elements
        navigation_terms = [
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
        ]
        if text in navigation_terms:
            return False

        # Skip standalone geographic terms
        geographic_terms = ["asia", "europe", "america", "africa", "australia"]
        if text in geographic_terms:
            return False

        # Skip very generic terms that aren't journals
        generic_terms = [
            "journals",
            "publications",
            "research",
            "science",
            "academic",
            "university",
            "institute",
            "press",
            "publisher",
            "publishing",
        ]
        if text in generic_terms:
            return False

        # Skip gambling/gaming terms that got scraped incorrectly
        gambling_terms = [
            "casino",
            "slots",
            "poker",
            "betting",
            "gaming",
            "games",
            "sport",
            "sports",
            "tembak ikan",
            "permainan",
        ]
        if any(term in text for term in gambling_terms):
            return False

        # Must contain typical journal indicators
        journal_indicators = [
            "journal",
            "review",
            "proceedings",
            "bulletin",
            "quarterly",
            "annual",
            "research",
            "studies",
            "science",
            "international",
            "european",
            "american",
            "asian",
            "global",
            "advances",
        ]

        # At least one journal indicator should be present
        if not any(indicator in text for indicator in journal_indicators):
            return False

        # Additional checks for realistic journal names
        words = text.split()

        # Skip single word entries unless they're clearly journal names
        if len(words) == 1:
            return False

        # Skip entries that are too long (likely concatenated text)
        if len(text) > 200:
            return False

        return True

    def is_valid_publisher_entry(self, text: str) -> bool:
        """Check if text looks like a valid publisher name.

        Args:
            text: Text to validate

        Returns:
            True if text appears to be a valid publisher name
        """
        if not text or len(text.strip()) < 2:
            return False

        text_lower = text.lower().strip()

        # Skip navigation and website elements
        navigation_terms = [
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
        if text_lower in navigation_terms:
            return False

        # Skip section headers
        if "hijacked" in text_lower or "how to" in text_lower:
            return False

        # Skip very generic single words that aren't publishers
        single_word_generic = ["journals", "publications", "academic", "research"]
        if len(text.split()) == 1 and text_lower in single_word_generic:
            return False

        # Publisher names are typically:
        # - Company names (ABC Journals, Academia Publishing)
        # - Organization names (Academic and Business Research Institute)
        # - Individual names (Abhinav)
        # - Branded names (The 5th Publisher)

        return True
