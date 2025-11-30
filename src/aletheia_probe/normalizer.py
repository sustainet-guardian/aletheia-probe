# SPDX-License-Identifier: MIT
"""Input normalization and validation for journal names and identifiers."""

import html
import re
from collections.abc import Callable

from .logging_config import get_detail_logger
from .models import QueryInput


class InputNormalizer:
    """Normalizes and validates journal names and identifiers."""

    def __init__(self) -> None:
        self.detail_logger = get_detail_logger()
        # Common journal name cleaning patterns
        self.cleanup_patterns = [
            (r"[^\w\s\-&().,:]", " "),  # Replace special characters with space
            (r"\s+", " "),  # Multiple whitespace to single space
            (r"\s*:\s*", ": "),  # Normalize colons
            (r"\s*-\s*", " - "),  # Normalize dashes
            (r"\s*&\s*", " & "),  # Normalize ampersands
        ]

        # Common acronyms that should remain uppercase
        self.acronyms = {
            "IEEE",
            "ACM",
            "SIGCOMM",
            "SIGCHI",
            "SIGKDD",
            "SIGMOD",
            "SIGPLAN",
            "VLDB",
            "ICML",
            "NIPS",
            "NEURIPS",
            "ICLR",
            "AAAI",
            "IJCAI",
            "CIKM",
            "WWW",
            "KDD",
            "ICDM",
            "SDM",
            "PAKDD",
            "ECML",
            "PKDD",
            "CLOUD",
            "NASA",
            "NIH",
            "NSF",
            "DARPA",
            "NIST",
            "ISO",
            "IEC",
            "ITU",
            "RFC",
            "HTTP",
            "TCP",
            "IP",
            "UDP",
            "DNS",
            "SSL",
            "TLS",
            "AI",
            "ML",
            "NLP",
            "CV",
            "HCI",
            "DB",
            "OS",
            "SE",
            "PL",
            "UK",
            "USA",
            "US",
            "EU",
            "UN",
            "WHO",
            "NATO",
        }

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

    def extract_conference_series(self, conference_name: str) -> str | None:
        """Extract conference series name by removing years and ordinals.

        This is a public interface for extracting the base series name from
        conference names that include years or ordinal numbers.

        Args:
            conference_name: Full conference name (may include year/ordinal)

        Returns:
            Conference series name if extractable, None otherwise

        Examples:
            >>> normalizer = InputNormalizer()
            >>> normalizer.extract_conference_series("34th ICML 2024")
            "ICML"
            >>> normalizer.extract_conference_series("2023 IEEE CVPR")
            "IEEE CVPR"
        """
        if not conference_name or not isinstance(conference_name, str):
            return None

        try:
            return self._extract_conference_series(conference_name.strip())
        except (AttributeError, ValueError, TypeError) as e:
            # Gracefully handle type errors and value errors in series extraction
            self.detail_logger.debug(
                f"Failed to extract conference series from '{conference_name}': {e}"
            )
            return None

    def normalize(
        self, raw_input: str, acronym_lookup: Callable[[str], str | None] | None = None
    ) -> QueryInput:
        """Normalize input and extract identifiers.

        Args:
            raw_input: Raw user input string
            acronym_lookup: Optional function to look up acronym expansions.
                           Should accept acronym (str) and return full name (str | None).

        Returns:
            QueryInput with normalized data and extracted identifiers
        """
        if not raw_input or not raw_input.strip():
            raise ValueError("Input cannot be empty")

        if len(raw_input) > 1000:
            raise ValueError("Input too long (maximum 1000 characters)")

        # Extract identifiers first
        identifiers = self._extract_identifiers(raw_input)

        # Extract conference/journal acronyms from parentheses before cleaning
        extracted_acronyms = self._extract_acronyms(raw_input)

        # Extract acronym mappings from parenthetical references for caller to persist
        # e.g., "International Conference on Machine Learning (ICML)" -> extract ICML mapping
        acronym_mappings = self._extract_acronym_mappings_from_text(
            raw_input, extracted_acronyms
        )

        # Clean and normalize the text
        normalized = self._clean_text(raw_input)
        normalized = self._expand_abbreviations(normalized)
        normalized = self._normalize_case(normalized)

        # Generate aliases
        aliases = self._generate_aliases(normalized)

        # Add extracted acronyms to aliases for better matching
        aliases.extend(extracted_acronyms)

        # Check if input looks like a standalone acronym and try to expand it
        acronym_expanded_from = None
        if self._is_standalone_acronym(raw_input.strip()) and acronym_lookup:
            expanded_name = acronym_lookup(raw_input.strip())
            if expanded_name:
                # Add expanded name as an alias
                aliases.append(expanded_name)
                acronym_expanded_from = raw_input.strip()

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_aliases: list[str] = []
        for alias in aliases:
            if alias not in seen:
                seen.add(alias)
                unique_aliases.append(alias)
        aliases = unique_aliases

        return QueryInput(
            raw_input=raw_input.strip(),
            normalized_name=normalized,
            identifiers=identifiers,
            aliases=aliases,
            acronym_expanded_from=acronym_expanded_from,
            extracted_acronym_mappings=acronym_mappings,
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

    def _extract_acronyms(self, text: str) -> list[str]:
        """Extract conference/journal acronyms from parentheses for use as aliases.

        Conference acronyms are typically uppercase letters, possibly with numbers,
        and appear in parentheses (e.g., CVPR, NeurIPS, ICCV, 3DV).

        Examples:
            "IEEE Conference on Computer Vision (CVPR)" -> ["CVPR"]
            "Neural Information Processing Systems (NeurIPS)" -> ["NeurIPS"]
            "Conference (ISSN: 1234-5678)" -> []  # Not an acronym

        Args:
            text: Input text that may contain parenthesized acronyms

        Returns:
            List of extracted acronyms
        """
        acronyms = []

        # Find all content within parentheses
        pattern = r"\(([^)]+)\)"
        matches = re.findall(pattern, text)

        for content in matches:
            content = content.strip()

            # Skip if contains certain keywords that indicate metadata, not acronyms
            skip_keywords = [
                "issn",
                "isbn",
                "doi",
                "online",
                "print",
                "invited",
                "accepted",
                "to appear",
            ]
            if any(keyword in content.lower() for keyword in skip_keywords):
                continue

            # Check if content looks like a conference/journal acronym:
            # - Primarily uppercase letters (allow some lowercase for mixed cases like NeurIPS)
            # - May contain numbers (e.g., 3DV, CVPR'23)
            # - May contain apostrophes for year indicators (e.g., CVPR'23)
            # - May contain hyphens (e.g., AAAI-23)
            # - Typically short (2-20 characters)
            # - Must start with uppercase letter
            # - No spaces, colons, or special punctuation

            # Pattern: starts with uppercase, contains mostly uppercase letters/numbers,
            # may have apostrophes, hyphens, or few lowercase letters
            if re.match(r"^[A-Z][A-Za-z0-9'\-]{1,19}$", content):
                # Additional check: should have a good proportion of uppercase letters
                # to avoid catching things like "(Online)" or "(Invited)"
                # Use 50% threshold to catch "NeurIPS" (57%) while excluding "Online" (17%)
                uppercase_count = sum(1 for c in content if c.isupper())
                total_alpha = sum(1 for c in content if c.isalpha())

                if total_alpha > 0 and (uppercase_count / total_alpha) >= 0.5:
                    acronyms.append(content)

        return acronyms

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text using regex patterns."""
        # Decode HTML entities first
        text = html.unescape(text)
        # Remove identifiers from text for name normalization
        text = self.issn_pattern.sub("", text)
        text = self.doi_pattern.sub("", text)

        # Remove content within brackets and parentheses that could interfere with matching
        text = self._remove_bracketed_content(text)

        # Apply cleanup patterns
        for pattern, replacement in self.cleanup_patterns:
            text = re.sub(pattern, replacement, text)

        return text.strip()

    def _remove_bracketed_content(self, text: str) -> str:
        """Remove content within brackets and parentheses that could interfere with journal matching.

        Examples:
            "Journal of Science (ISSN: 1234-5678)" -> "Journal of Science"
            "{{IEEE}} Conference on {{Cloud Computing}} ({{CLOUD}})" -> "IEEE Conference on Cloud Computing"
            "Advances in Neural Information Processing Systems (NeurIPS)" -> "Advances in Neural Information Processing Systems"

        Args:
            text: Input text that may contain bracketed content

        Returns:
            Text with bracketed content removed and whitespace normalized
        """
        # Remove nested curly braces (BibTeX formatting) - handle multiple levels
        # This handles cases like {{IEEE}} -> IEEE
        while re.search(r"\{[^{}]*\}", text):
            text = re.sub(r"\{([^{}]*)\}", r"\1", text)

        # Remove content within square brackets [...]
        # This handles abbreviations and annotations like [2023], [Online]
        text = re.sub(r"\[[^\]]*\]", "", text)

        # Remove content within parentheses (...)
        # This handles journal/conference abbreviations like (NeurIPS), (CLOUD)
        text = re.sub(r"\([^)]*\)", "", text)

        # Clean up multiple spaces left by bracket removal
        text = re.sub(r"\s+", " ", text)

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
            # Check if word is a known acronym (case-insensitive)
            if word.upper() in self.acronyms:
                normalized_words.append(word.upper())
            # Keep certain words lowercase unless at start
            elif i > 0 and word.lower() in [
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

    def _is_standalone_acronym(self, text: str) -> bool:
        """Check if input looks like a standalone acronym.

        Args:
            text: Input text to check

        Returns:
            True if text appears to be an acronym (short, mostly uppercase)
        """
        # Must be reasonably short (2-10 characters)
        if len(text) < 2 or len(text) > 10:
            return False

        # Remove common punctuation/symbols for checking
        clean_text = text.replace("&", "").replace("'", "").replace("-", "").strip()

        # Must have at least some letters
        if not any(c.isalpha() for c in clean_text):
            return False

        # Calculate proportion of uppercase letters
        alpha_chars = [c for c in clean_text if c.isalpha()]
        if not alpha_chars:
            return False

        uppercase_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)

        # Must be at least 50% uppercase to be considered an acronym
        return uppercase_ratio >= 0.5

    def _extract_acronym_mappings_from_text(
        self, text: str, extracted_acronyms: list[str]
    ) -> dict[str, str]:
        """Extract acronym mappings when text contains both full name and acronym.

        For example: "International Conference on Machine Learning (ICML)"
        will return: {"ICML": "International Conference on Machine Learning"}

        Args:
            text: Original text that may contain acronyms in parentheses
            extracted_acronyms: List of acronyms extracted from the text

        Returns:
            Dictionary mapping acronyms to their full names
        """
        mappings: dict[str, str] = {}

        if not extracted_acronyms:
            return mappings

        # For each acronym, try to extract the full name before the parentheses
        for acronym in extracted_acronyms:
            # Find the acronym in parentheses
            pattern = rf"\(([^)]*{re.escape(acronym)}[^)]*)\)"
            match = re.search(pattern, text)

            if match:
                # Extract text before the parentheses
                # Get the position of the match
                match_start = match.start()

                # Get text before the acronym
                text_before = text[:match_start].strip()

                if text_before:
                    # Clean up the text (remove extra whitespace, quotes, etc.)
                    full_name = text_before.strip("'\"").strip()

                    # Only include if we have a reasonable full name (longer than the acronym)
                    if full_name and len(full_name) > len(acronym) * 2:
                        mappings[acronym] = full_name

        return mappings


# Global normalizer instance
input_normalizer = InputNormalizer()
