# SPDX-License-Identifier: MIT
"""Text cleaning utilities for Beall's List data."""

import html
import re


class JournalNameCleaner:
    """Cleans and normalizes journal names from Beall's List."""

    def clean_malformed_text(self, text: str) -> str:
        """Clean malformed text entries.

        Removes quotes, HTML entities, special characters, and normalizes whitespace.

        Args:
            text: Raw text to clean

        Returns:
            Cleaned text
        """
        # Remove quotes at start/end
        text = text.strip("'\"")

        # Decode HTML entities first (&amp; -> &, &lt; -> <, etc.)
        text = html.unescape(text)

        # Replace multiple whitespace (including tabs, newlines) with single space
        text = re.sub(r"\s+", " ", text)

        # Remove HTML entities and special characters
        text = text.replace("\xa0", " ")  # Non-breaking space
        text = text.replace("\u200b", "")  # Zero-width space
        text = re.sub(r"[^\w\s\-&().,:]", " ", text)  # Remove other special chars
        text = re.sub(r"\s+", " ", text)  # Clean up multiple spaces again

        return text.strip()
