"""Input normalization and validation for journal names and identifiers."""

import re

from .models import QueryInput


class InputNormalizer:
    """Normalizes and validates journal names and identifiers."""

    def __init__(self) -> None:
        # Common journal name cleaning patterns
        self.cleanup_patterns = [
            (r"[^\w\s\-&().,:]", " "),  # Replace special characters with space
            (r"\s+", " "),  # Multiple whitespace to single space
            (r"\s*:\s*", ": "),  # Normalize colons
            (r"\s*-\s*", " - "),  # Normalize dashes
            (r"\s*&\s*", " & "),  # Normalize ampersands
        ]

        # Common abbreviation expansions
        self.abbreviations = {
            "J.": "Journal",
            "Jrnl": "Journal",
            "Int.": "International",
            "Intl": "International",
            "Nat.": "National",
            "Sci.": "Science",
            "Tech.": "Technology",
            "Rev.": "Review",
            "Res.": "Research",
            "Proc.": "Proceedings",
            "Trans.": "Transactions",
            "Ann.": "Annual",
            "Q.": "Quarterly",
        }

        # ISSN pattern
        self.issn_pattern = re.compile(r"\b(\d{4})-?(\d{3}[\dX])\b")

        # DOI pattern
        self.doi_pattern = re.compile(r"\b10\.\d{4,}[^\s]*\b")

    def normalize(self, raw_input: str) -> QueryInput:
        """Normalize input and extract identifiers.

        Args:
            raw_input: Raw user input string

        Returns:
            QueryInput with normalized data and extracted identifiers
        """
        if not raw_input or not raw_input.strip():
            raise ValueError("Input cannot be empty")

        if len(raw_input) > 1000:
            raise ValueError("Input too long (maximum 1000 characters)")

        # Extract identifiers first
        identifiers = self._extract_identifiers(raw_input)

        # Clean and normalize the text
        normalized = self._clean_text(raw_input)
        normalized = self._expand_abbreviations(normalized)
        normalized = self._normalize_case(normalized)

        # Generate aliases
        aliases = self._generate_aliases(normalized)

        return QueryInput(
            raw_input=raw_input.strip(),
            normalized_name=normalized,
            identifiers=identifiers,
            aliases=aliases,
        )

    def _extract_identifiers(self, text: str) -> dict[str, str]:
        """Extract ISSN, DOI, and other identifiers from text."""
        identifiers = {}

        # Extract ISSN
        issn_matches = self.issn_pattern.findall(text)
        if issn_matches:
            # Take the first ISSN found
            issn = f"{issn_matches[0][0]}-{issn_matches[0][1]}"
            identifiers["issn"] = issn

        # Extract DOI
        doi_matches = self.doi_pattern.findall(text)
        if doi_matches:
            identifiers["doi"] = doi_matches[0]

        return identifiers

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text using regex patterns."""
        # Remove identifiers from text for name normalization
        text = self.issn_pattern.sub("", text)
        text = self.doi_pattern.sub("", text)

        # Apply cleanup patterns
        for pattern, replacement in self.cleanup_patterns:
            text = re.sub(pattern, replacement, text)

        return text.strip()

    def _expand_abbreviations(self, text: str) -> str:
        """Expand common journal abbreviations."""
        words = text.split()
        expanded_words = []

        for word in words:
            # Check for abbreviation (word ending with period)
            if word in self.abbreviations:
                expanded_words.append(self.abbreviations[word])
            else:
                expanded_words.append(word)

        return " ".join(expanded_words)

    def _normalize_case(self, text: str) -> str:
        """Normalize case using title case with special handling."""
        # Title case with special handling for certain words
        words = text.split()
        normalized_words = []

        for i, word in enumerate(words):
            # Keep certain words lowercase unless at start
            if i > 0 and word.lower() in [
                "of",
                "and",
                "or",
                "the",
                "in",
                "on",
                "at",
                "to",
                "for",
                "with",
            ]:
                normalized_words.append(word.lower())
            else:
                # Title case
                normalized_words.append(word.capitalize())

        return " ".join(normalized_words)

    def _generate_aliases(self, normalized_name: str) -> list[str]:
        """Generate common aliases for the journal/conference name."""
        aliases = []

        # Add version without "Journal of" prefix
        if normalized_name.lower().startswith("journal of "):
            aliases.append(normalized_name[11:])

        # Add version without "The" prefix
        if normalized_name.lower().startswith("the "):
            aliases.append(normalized_name[4:])

        # Add version without "Proceedings of" prefix (for conferences)
        if normalized_name.lower().startswith("proceedings of "):
            aliases.append(normalized_name[15:])

        # Add conference series name (strip year/ordinal patterns)
        series_name = self._extract_conference_series(normalized_name)
        if series_name and series_name != normalized_name:
            aliases.append(series_name)

        # Add version with abbreviated journal words
        abbreviated = self._create_abbreviated_version(normalized_name)
        if abbreviated != normalized_name:
            aliases.append(abbreviated)

        # Remove duplicates and empty strings
        aliases = [alias.strip() for alias in aliases if alias.strip()]
        aliases = list(set(aliases))

        return aliases

    def _create_abbreviated_version(self, text: str) -> str:
        """Create abbreviated version by reversing some expansions."""
        # Reverse some common expansions for alias generation
        reverse_abbreviations = {v: k for k, v in self.abbreviations.items()}

        words = text.split()
        abbreviated_words = []

        for word in words:
            if word in reverse_abbreviations:
                abbreviated_words.append(reverse_abbreviations[word])
            else:
                abbreviated_words.append(word)

        return " ".join(abbreviated_words)

    def _extract_conference_series(self, text: str) -> str | None:
        """Extract conference series name by removing years and ordinals.

        Examples:
            "2018 IEEE 11th International Conference on Cloud Computing (CLOUD)" -> "IEEE International Conference on Cloud Computing (CLOUD)"
            "Proceedings of Semantic Web Information Management on Semantic Web Information Management" -> "Semantic Web Information Management on Semantic Web Information Management"

        Args:
            text: Conference name text

        Returns:
            Conference series name if extractable, None otherwise
        """
        # Pattern to match year at start or in conference name (e.g., "2018", "2018/19")
        year_pattern = r"\b(19|20)\d{2}(/\d{2})?\b"

        # Pattern to match ordinals (e.g., "11th", "1st", "2nd", "3rd")
        ordinal_pattern = r"\b\d+(st|nd|rd|th)\b"

        # Pattern to match "Proceedings of" prefix
        proceedings_pattern = r"^proceedings\s+of\s+"

        # Remove patterns
        series = text
        series = re.sub(year_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(ordinal_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(proceedings_pattern, "", series, flags=re.IGNORECASE)

        # Clean up extra whitespace
        series = re.sub(r"\s+", " ", series).strip()

        # Only return if we actually removed something
        if series != text and series:
            return series

        return None


# Global normalizer instance
input_normalizer = InputNormalizer()
