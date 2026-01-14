# SPDX-License-Identifier: MIT
"""Input normalization and validation for journal names and identifiers."""

import html
import re
from collections.abc import Callable

from .logging_config import get_detail_logger
from .models import QueryInput


# Normalization and Validation constants
MAX_INPUT_LENGTH: int = 1000
ACRONYM_UPPERCASE_THRESHOLD: float = 0.5
MIN_ACRONYM_MAPPING_LENGTH_MULTIPLIER: int = 2
MIN_ACRONYM_LENGTH: int = 2
MAX_ACRONYM_LENGTH: int = 20
MAX_STANDALONE_ACRONYM_LENGTH: int = 10

# Conference name normalization and comparison
MIN_CONFERENCE_NAME_LENGTH_FOR_SUBSTRING_MATCH: int = 10

# Prefix strings for normalization
PREFIX_JOURNAL_OF: str = "Journal of "
JOURNAL_OF_PREFIX_LENGTH: int = len(PREFIX_JOURNAL_OF)
PREFIX_THE: str = "The "
THE_PREFIX_LENGTH: int = len(PREFIX_THE)
PREFIX_PROCEEDINGS_OF: str = "Proceedings of "
PROCEEDINGS_OF_PREFIX_LENGTH: int = len(PREFIX_PROCEEDINGS_OF)

# Text cleaning patterns
NORMALIZER_CLEANUP_PATTERNS: list[tuple[str, str]] = [
    (r"[^\w\s\-&().,:]", " "),  # Replace special characters with space
    (r"\s+", " "),  # Multiple whitespace to single space
    (r"\s*:\s*", ": "),  # Normalize colons
    (r"\s*-\s*", " - "),  # Normalize dashes
    (r"\s*&\s*", " & "),  # Normalize ampersands
]

# Common acronyms that should remain uppercase
COMMON_ACRONYMS: set[str] = {
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

# Edge-case abbreviations that cannot be learned automatically
# (because the abbreviated form is not a prefix of the expanded form,
# or they are acronyms rather than prefix abbreviations)
# All other abbreviations are learned dynamically and stored in the database.
COMMON_ABBREVIATIONS: dict[str, str] = {
    "Jrnl": "Journal",  # Not a prefix - can't be learned
    "Intl": "International",  # Not a prefix - can't be learned
    "intl.": "international",  # Not a prefix - can't be learned
    "AI": "Artificial Intelligence",  # Acronym - can't be learned as prefix
}

# Keywords that indicate metadata, not acronyms
ACRONYM_SKIP_KEYWORDS: set[str] = {
    "issn",
    "isbn",
    "doi",
    "online",
    "print",
    "invited",
    "accepted",
    "to appear",
}

# Common words to ignore for comparison (e.g., "journal of", "the")
STOP_WORDS: set[str] = {
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
    "journal",
    "international",
    "conference",
    "proceedings",
}


class InputNormalizer:
    """Normalizes and validates journal names and identifiers."""

    def __init__(self) -> None:
        self.detail_logger = get_detail_logger()
        # Common journal name cleaning patterns
        self.cleanup_patterns = NORMALIZER_CLEANUP_PATTERNS

        # Common acronyms that should remain uppercase
        self.acronyms = COMMON_ACRONYMS

        # Common abbreviation expansions
        self.abbreviations = COMMON_ABBREVIATIONS

        # ISSN pattern
        self.issn_pattern = re.compile(r"\b(\d{4})-?(\d{3}[\dX])\b")

        # DOI pattern
        self.doi_pattern = re.compile(r"\b10\.\d{4,}[^\s]*\b")

        # Acronym pattern for extraction from parentheses
        self.acronym_pattern = re.compile(
            rf"^[A-Z][A-Za-z0-9'\-]{{{MIN_ACRONYM_LENGTH - 1},{MAX_ACRONYM_LENGTH - 1}}}$"
        )

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

        if len(raw_input) > MAX_INPUT_LENGTH:
            raise ValueError(f"Input too long (maximum {MAX_INPUT_LENGTH} characters)")

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
        normalized = normalize_case(normalized)

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

    def _is_valid_acronym_format(self, text: str) -> bool:
        """Check if text has a valid acronym format (mostly uppercase).

        Args:
            text: Text to check

        Returns:
            True if valid acronym format
        """
        # Calculate proportion of uppercase letters
        alpha_chars = [c for c in text if c.isalpha()]
        if not alpha_chars:
            return False

        uppercase_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)

        # Must be at least ACRONYM_UPPERCASE_THRESHOLD to be considered an acronym
        return uppercase_ratio >= ACRONYM_UPPERCASE_THRESHOLD

    def _extract_acronyms(self, text: str) -> list[str]:
        """Extract conference/journal acronyms from parentheses for use as aliases.

        Conference acronyms are typically uppercase letters, possibly with numbers,
        and appear in parentheses (e.g., CVPR, NeurIPS, ICCV, 3DV).

        Examples:
            "IEEE Conference on Computer Vision (CVPR)" -> ["CVPR"]
            "Neural Information Processing Systems (NeurIPS)" -> ["NeurIPS"]
            "Conference (ISSN: 1234-5679)" -> []  # Not an acronym

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
            if any(keyword in content.lower() for keyword in ACRONYM_SKIP_KEYWORDS):
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
            if self.acronym_pattern.match(content):
                # Additional check: should have a good proportion of uppercase letters
                # to avoid catching things like "(Online)" or "(Invited)"
                if self._is_valid_acronym_format(content):
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
            "Journal of Science (ISSN: 1234-5679)" -> "Journal of Science"
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
        """Expand abbreviations using learned mappings from database and edge-case fallbacks."""
        # Lazy load learned abbreviations from database
        if not hasattr(self, "_learned_abbrevs_cache"):
            try:
                from .cache.acronym_cache import AcronymCache

                cache = AcronymCache()
                # Get learned abbreviations as dict: abbrev -> [(expanded, confidence), ...]
                self._learned_abbrevs_cache = cache.get_learned_abbreviations()
            except Exception:
                self._learned_abbrevs_cache = {}

        words = text.split()
        expanded_words = []

        for word in words:
            # First check learned abbreviations from database (use highest confidence match)
            word_lower = word.lower()
            if word_lower in self._learned_abbrevs_cache:
                expansions = self._learned_abbrevs_cache[word_lower]
                if expansions:
                    # Use the expansion with highest confidence
                    best_expansion = expansions[0][0]  # Already sorted by confidence
                    # Preserve original case if first letter was uppercase
                    if word[0].isupper():
                        best_expansion = best_expansion.capitalize()
                    expanded_words.append(best_expansion)
                    continue

            # Fall back to edge-case abbreviations (non-learnable ones)
            if word in self.abbreviations:
                expanded_words.append(self.abbreviations[word])
            else:
                expanded_words.append(word)

        return " ".join(expanded_words)

    def _generate_aliases(self, normalized_name: str) -> list[str]:
        """Generate common aliases for the journal/conference name."""
        aliases = []

        # Add version without "Journal of" prefix
        if normalized_name.lower().startswith(PREFIX_JOURNAL_OF.lower()):
            aliases.append(normalized_name[JOURNAL_OF_PREFIX_LENGTH:])

        # Add version without "The" prefix
        if normalized_name.lower().startswith(PREFIX_THE.lower()):
            aliases.append(normalized_name[THE_PREFIX_LENGTH:])

        # Add version without "Proceedings of" prefix (for conferences)
        if normalized_name.lower().startswith(PREFIX_PROCEEDINGS_OF.lower()):
            aliases.append(normalized_name[PROCEEDINGS_OF_PREFIX_LENGTH:])

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

        # Pattern to match spelled-out ordinals (e.g., "first", "second", "third")
        spelled_ordinal_pattern = (
            r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
            r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|"
            r"seventeenth|eighteenth|nineteenth|twentieth|"
            r"twenty-first|twenty-second|twenty-third|twenty-fourth|twenty-fifth|"
            r"twenty-sixth|twenty-seventh|twenty-eighth|twenty-ninth|thirtieth|"
            r"thirty-first|thirty-second|thirty-third|thirty-fourth|thirty-fifth|"
            r"thirty-sixth|thirty-seventh|thirty-eighth|thirty-ninth|fortieth|fiftieth|sixtieth)\b"
        )

        # Pattern to match embedded year markers (French/other languages: "28e", "29e", "1re", "2ème")
        embedded_year_pattern = r"\b\d{1,2}(e|re|ème|è)\b"

        # Pattern to match edition markers
        edition_pattern = r"\b(edition|ed\.)\s+\d{4}\b|\b\d{4}\s+(edition|ed\.)\b"

        # Pattern to match "Proceedings of" prefix
        proceedings_pattern = r"^proceedings\s+of\s+"

        # Remove patterns
        series = text
        series = re.sub(year_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(ordinal_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(spelled_ordinal_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(embedded_year_pattern, "", series, flags=re.IGNORECASE)
        series = re.sub(edition_pattern, "", series, flags=re.IGNORECASE)
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
        # Must be reasonably short
        if len(text) < MIN_ACRONYM_LENGTH or len(text) > MAX_STANDALONE_ACRONYM_LENGTH:
            return False

        # Remove common punctuation/symbols for checking
        clean_text = text.replace("&", "").replace("'", "").replace("-", "").strip()

        return self._is_valid_acronym_format(clean_text)

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
                    if (
                        full_name
                        and len(full_name)
                        > len(acronym) * MIN_ACRONYM_MAPPING_LENGTH_MULTIPLIER
                    ):
                        mappings[acronym] = full_name

        return mappings


def normalize_case(text: str) -> str:
    """Normalize case using title case with special handling for acronyms.

    Args:
        text: Text to normalize

    Returns:
        Text with normalized case (title case with special acronym handling)
    """
    words = text.split()
    normalized_words = []

    for i, word in enumerate(words):
        # Check if word is a known acronym (case-insensitive)
        if word.upper() in COMMON_ACRONYMS:
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


def normalize_for_comparison(text: str) -> str:
    """Normalize text for robust comparison, removing common words and special characters.

    Args:
        text: The input string (e.g., a journal or conference name).

    Returns:
        A cleaned and normalized string suitable for comparison.
    """
    text = html.unescape(text)
    text = text.lower()

    # Remove organization prefixes (IEEE, ACM, etc.) for better comparison
    org_prefix_pattern = r"^(ieee|acm|aaai|aaas|acl|springer|elsevier|ieee/cvf)\s+"
    text = re.sub(org_prefix_pattern, "", text, flags=re.IGNORECASE)

    # Replace hyphens with spaces before removing special characters
    # This ensures "high-performance" matches "high performance"
    text = text.replace("-", " ")

    # Remove common special characters, keeping only alphanumeric and spaces
    text = re.sub(r"[^\w\s]", "", text)
    words = [word for word in text.split() if word not in STOP_WORDS]
    return " ".join(words)


def are_conference_names_equivalent(name1: str, name2: str) -> bool:
    """Check if two conference names are essentially the same with minor variations.

    This function uses the existing conference series normalization logic to
    identify trivial differences like year prefixes/suffixes and ordinal numbers
    that don't represent different conferences. It also uses a more robust
    comparison by normalizing the names to remove stop words and special characters.

    Args:
        name1: First conference name
        name2: Second conference name

    Returns:
        True if the names represent the same conference with minor variations

    Examples:
        - "2022 IEEE/CVF Conference" and "IEEE/CVF Conference" -> True
        - "Conference 2022" and "Conference" -> True
        - "1st International Conference" and "International Conference" -> True
        - "AAAI" and "AI Conference" -> False
        - "journal of process management and new technologies international" and "journal of process management new technologies international" -> True
    """
    # Perform a quick comparison after aggressive normalization first
    normalized_for_comp1 = normalize_for_comparison(name1)
    normalized_for_comp2 = normalize_for_comparison(name2)

    if normalized_for_comp1 == normalized_for_comp2:
        return True

    # Normalize case
    norm1 = name1.lower().strip()
    norm2 = name2.lower().strip()

    # If identical after case normalization, they're equivalent
    if norm1 == norm2:
        return True

    # Use the existing conference series extraction logic
    # This removes years, ordinals, and "Proceedings of" prefix
    series1 = input_normalizer.extract_conference_series(norm1)
    series2 = input_normalizer.extract_conference_series(norm2)

    # If both extracted to the same series, they're equivalent
    if series1 and series2:
        if normalize_for_comparison(series1) == normalize_for_comparison(series2):
            return True

    # Handle case where one might be the series of the other
    # e.g., "2022 Conference" vs "Conference" where series2 is None
    # Apply robust comparison here as well
    if series1 and normalize_for_comparison(series1) == normalized_for_comp2:
        return True
    if series2 and normalize_for_comparison(series2) == normalized_for_comp1:
        return True

    # Check if one is a substring of the other after normalization
    # But only if the shorter name meets minimum length to avoid false positives
    # (e.g., "AI" vs "AAAI" should not match)
    # Apply robust comparison here as well
    if (
        len(normalized_for_comp1) >= MIN_CONFERENCE_NAME_LENGTH_FOR_SUBSTRING_MATCH
        or len(normalized_for_comp2) >= MIN_CONFERENCE_NAME_LENGTH_FOR_SUBSTRING_MATCH
    ):
        if (
            normalized_for_comp1 in normalized_for_comp2
            or normalized_for_comp2 in normalized_for_comp1
        ):
            return True

    return False


def are_variants_of_same_venue(
    variant1: str,
    variant2: str,
    learned_abbrevs: dict[str, list[tuple[str, float]]],
) -> bool:
    """Check if two venue name variants represent the same venue using learned abbreviations.

    This function extends are_conference_names_equivalent() by expanding abbreviated
    forms using learned abbreviation mappings. It handles cases like:
    - "int. conf." vs "international conference"
    - "modelling" vs "modeling" (spelling variants)
    - Multiple expansions per abbreviation (e.g., "int." → "international" or "integer")

    Args:
        variant1: First venue name variant
        variant2: Second venue name variant
        learned_abbrevs: Dictionary mapping abbreviated forms to list of
                        (expanded_form, confidence) tuples

    Returns:
        True if variants represent the same venue, False otherwise

    Examples:
        >>> abbrevs = {"int.": [("international", 0.9)], "conf.": [("conference", 0.95)]}
        >>> are_variants_of_same_venue(
        ...     "ieee int. conf. testing",
        ...     "ieee international conference testing",
        ...     abbrevs
        ... )
        True
    """
    # Step 1: Try existing equivalence check first
    if are_conference_names_equivalent(variant1, variant2):
        return True

    # Step 2: Merge learned abbreviations with edge-case static abbreviations
    # COMMON_ABBREVIATIONS contains non-learnable cases like "intl." -> "international"
    all_abbrevs = dict(learned_abbrevs) if learned_abbrevs else {}
    for abbrev, expanded in COMMON_ABBREVIATIONS.items():
        abbrev_lower = abbrev.lower()
        if abbrev_lower not in all_abbrevs:
            all_abbrevs[abbrev_lower] = [(expanded.lower(), 0.9)]

    if not all_abbrevs:
        return False  # No abbreviations to expand

    # Tokenize both variants
    tokens1 = variant1.lower().split()
    tokens2 = variant2.lower().split()

    # Find tokens in variant1 that might be abbreviations
    tokens_to_expand = []
    for i, token in enumerate(tokens1):
        if token in all_abbrevs and all_abbrevs[token]:
            tokens_to_expand.append((i, token, all_abbrevs[token]))

    # If no abbreviations found, cannot match via expansion
    if not tokens_to_expand:
        # Try the reverse: maybe variant2 has abbreviations
        tokens1, tokens2 = tokens2, tokens1
        tokens_to_expand = []
        for i, token in enumerate(tokens1):
            if token in all_abbrevs and all_abbrevs[token]:
                tokens_to_expand.append((i, token, all_abbrevs[token]))

        if not tokens_to_expand:
            return False  # No abbreviations to expand in either direction

    # Step 3: Expand ALL abbreviations at once (using highest confidence expansion)
    # This handles cases like "Amer. Contr. Conf." -> "American Control Conference"
    expanded_tokens = tokens1.copy()
    for idx, _abbrev, expansions in tokens_to_expand:
        # Use the highest confidence expansion (first in list, already sorted)
        if expansions:
            expanded_tokens[idx] = expansions[0][0]  # (expanded_form, confidence)

    expanded_variant = " ".join(expanded_tokens)

    # Compare fully expanded version with variant2
    if are_conference_names_equivalent(expanded_variant, " ".join(tokens2)):
        return True

    return False


# Global normalizer instance
input_normalizer = InputNormalizer()
