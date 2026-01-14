# SPDX-License-Identifier: MIT
"""Abbreviation learning module for discovering venue name abbreviation patterns.

This module implements a self-learning system that discovers abbreviation mappings
by analyzing pairs of venue name variants. It uses sequence alignment to identify
patterns like "int." → "international" and "conf." → "conference".
"""

import difflib

from .logging_config import get_detail_logger


detail_logger = get_detail_logger()


def tokenize(text: str) -> list[str]:
    """Tokenize text into words, preserving periods at end of words.

    Strips trailing punctuation except periods (which are meaningful for
    abbreviations like "conf." or "int.").

    Args:
        text: Text to tokenize

    Returns:
        List of tokens

    Examples:
        >>> tokenize("ieee int. conf. image")
        ['ieee', 'int.', 'conf.', 'image']
        >>> tokenize("ieee international conference on image processing")
        ['ieee', 'international', 'conference', 'on', 'image', 'processing']
        >>> tokenize("computers, networks, and systems")
        ['computers', 'networks', 'systems']
    """
    # Split on whitespace
    tokens = text.lower().split()
    # Strip trailing punctuation except periods (which indicate abbreviations)
    cleaned_tokens = []
    for token in tokens:
        # Strip trailing punctuation except period
        cleaned = token.rstrip(",;:!?")
        if cleaned:  # Skip empty tokens
            cleaned_tokens.append(cleaned)
    return cleaned_tokens


def is_valid_abbreviation(abbrev: str, full: str) -> bool:
    """Check if abbrev is a valid abbreviation of full.

    Recognizes three patterns:
    1. Period-terminated prefix: "int." → "international"
    2. Acronym-style: "CV" → "Computer Vision" (first letters)
    3. Spelling variants: "modelling" ↔ "modeling" (high similarity)

    Args:
        abbrev: Potential abbreviated form
        full: Potential expanded form

    Returns:
        True if abbrev is a valid abbreviation of full
    """
    # Pattern 1: Ends with period and is prefix
    # "int." is abbreviation of "international"
    if abbrev.endswith("."):
        prefix = abbrev[:-1].lower()
        if full.lower().startswith(prefix) and len(full) > len(prefix) + 2:
            return True

    # Pattern 2: Acronym-style (first letters)
    # "CV" could be "Computer Vision"
    if abbrev.isupper() and len(abbrev) >= 2:
        words = [
            w
            for w in full.split()
            if w and w.lower() not in {"a", "an", "the", "of", "in", "on", "for"}
        ]
        if words:
            first_letters = "".join(word[0] for word in words)
            if abbrev.lower() == first_letters.lower():
                return True

    # Pattern 3: Spelling variants (modelling ↔ modeling)
    # Similar strings with small edit distance
    if not abbrev.endswith(".") and len(abbrev) > 3 and len(full) > 3:
        # Strip punctuation to compare actual content
        abbrev_clean = abbrev.lower().rstrip(".,;:!?")
        full_clean = full.lower().rstrip(".,;:!?")

        # Skip if they're identical after stripping punctuation
        if abbrev_clean == full_clean:
            return False

        # Skip if one is just the plural of the other (singular/plural difference)
        # e.g., "computer" vs "computers" is not a spelling variant
        if abbrev_clean + "s" == full_clean or full_clean + "s" == abbrev_clean:
            return False
        if abbrev_clean + "es" == full_clean or full_clean + "es" == abbrev_clean:
            return False

        # Calculate similarity ratio
        similarity = difflib.SequenceMatcher(None, abbrev_clean, full_clean).ratio()
        # High similarity but not identical → likely spelling variant
        if similarity > 0.85:
            return True

    return False


def calculate_initial_confidence(abbrev: str, full: str) -> float:
    """Calculate initial confidence for this mapping.

    Args:
        abbrev: Abbreviated form
        full: Expanded form

    Returns:
        Initial confidence score (0.0-1.0)
    """
    abbrev_clean = abbrev.rstrip(".")

    # Perfect prefix match → high confidence
    if full.lower().startswith(abbrev_clean.lower()):
        prefix_ratio = len(abbrev_clean) / len(full)
        if prefix_ratio > 0.5:
            # Very long prefix relative to full word (uncommon)
            return 0.7
        else:
            # Normal prefix abbreviation
            return 0.5

    # Acronym match → medium confidence
    words = [
        w
        for w in full.split()
        if w and w.lower() not in {"a", "an", "the", "of", "in", "on", "for"}
    ]
    if words:
        first_letters = "".join(word[0] for word in words)
        if abbrev.lower() == first_letters.lower():
            return 0.6

    # Spelling variant → medium-high confidence
    if not abbrev.endswith(".") and len(abbrev) > 3 and len(full) > 3:
        similarity = difflib.SequenceMatcher(None, abbrev.lower(), full.lower()).ratio()
        if similarity > 0.85:
            return 0.7  # Spelling variants are usually reliable

    # Low initial confidence (edge case)
    return 0.3


def learn_abbreviations_from_pair(
    short: str, long: str
) -> list[tuple[str, str, float]]:
    """Discover abbreviation mappings by aligning token sequences.

    Compares two venue name variants and identifies potential abbreviation
    patterns using sequence alignment. Detects:
    - Period-terminated abbreviations: "int." → "international"
    - Acronyms: "CV" → "Computer Vision"
    - Spelling variants: "modelling" ↔ "modeling"

    Args:
        short: Potentially abbreviated form (e.g., "ieee int. conf. image process.")
        long: Potentially expanded form (e.g., "ieee international conference on image processing")

    Returns:
        List of (abbreviated_form, expanded_form, initial_confidence) tuples

    Examples:
        >>> learn_abbreviations_from_pair(
        ...     "ieee int. conf. image process.",
        ...     "ieee international conference on image processing"
        ... )
        [('int.', 'international', 0.5), ('conf.', 'conference', 0.5), ('process.', 'processing', 0.5)]
    """
    # 1. Tokenize both strings
    short_tokens = tokenize(short)
    long_tokens = tokenize(long)

    detail_logger.debug(f"Comparing tokens: {short_tokens} vs {long_tokens}")

    # 2. Align sequences using difflib.SequenceMatcher
    matcher = difflib.SequenceMatcher(None, short_tokens, long_tokens)
    mappings = []

    # 3. Analyze alignment operations
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            # Potential abbreviation or spelling variant
            short_chunk = short_tokens[i1:i2]
            long_chunk = long_tokens[j1:j2]

            detail_logger.debug(f"Potential abbreviation: {short_chunk} → {long_chunk}")

            # Handle n-to-n token replacements (when chunks are same length)
            # This handles cases like ['intl.', 'conf.'] -> ['international', 'conference']
            if len(short_chunk) == len(long_chunk):
                for abbrev, full in zip(short_chunk, long_chunk, strict=True):
                    # Check if it's a valid abbreviation pattern
                    if is_valid_abbreviation(abbrev, full):
                        confidence = calculate_initial_confidence(abbrev, full)
                        mappings.append((abbrev, full, confidence))
                        detail_logger.debug(
                            f"  ✓ Valid abbreviation: '{abbrev}' → '{full}' (confidence: {confidence:.2f})"
                        )

                        # For spelling variants, also store reverse mapping
                        if not abbrev.endswith(".") and not full.endswith("."):
                            similarity = difflib.SequenceMatcher(
                                None, abbrev.lower(), full.lower()
                            ).ratio()
                            if similarity > 0.85:
                                # Bidirectional for spelling variants
                                mappings.append((full, abbrev, confidence))
                                detail_logger.debug(
                                    f"  ✓ Bidirectional variant: '{full}' ↔ '{abbrev}'"
                                )
                    else:
                        detail_logger.debug(
                            f"  ✗ Not a valid abbreviation: '{abbrev}' vs '{full}'"
                        )

        elif tag == "delete":
            # Token only in short form (probably not abbreviation, might be error)
            detail_logger.debug(
                f"Token only in short form: {short_tokens[i1:i2]} (ignored)"
            )

        elif tag == "insert":
            # Token only in long form (probably stop word or additional descriptor)
            detail_logger.debug(
                f"Token only in long form: {long_tokens[j1:j2]} (likely stop word)"
            )

    detail_logger.debug(f"Discovered {len(mappings)} abbreviation mappings")
    return mappings
