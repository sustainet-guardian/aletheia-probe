# SPDX-License-Identifier: MIT
"""Standard confidence scoring utilities for backends."""

from enum import Enum, auto


class MatchQuality(Enum):
    """Quality of a match found by a backend."""

    EXACT_ISSN = auto()
    EXACT_NAME = auto()
    EXACT_ALIAS = auto()
    SUBSTRING_MATCH = auto()
    WORD_SIMILARITY = auto()
    FUZZY_MATCH = auto()
    NO_MATCH = auto()


def calculate_base_confidence(match_quality: MatchQuality) -> float:
    """Get the base confidence score for a given match quality.

    Args:
        match_quality: The quality level of the match

    Returns:
        Base confidence score (0.0-1.0)
    """
    if match_quality == MatchQuality.EXACT_ISSN:
        return 1.0
    elif match_quality == MatchQuality.EXACT_NAME:
        return 0.95
    elif match_quality == MatchQuality.EXACT_ALIAS:
        return 0.90
    elif match_quality == MatchQuality.SUBSTRING_MATCH:
        return 0.70
    elif match_quality == MatchQuality.WORD_SIMILARITY:
        return 0.60
    elif match_quality == MatchQuality.FUZZY_MATCH:
        return 0.50
    else:
        return 0.0


def calculate_name_similarity(
    query_name: str, match_name: str, method: str = "jaccard"
) -> float:
    """Calculate similarity between two names.

    Args:
        query_name: The name searched for
        match_name: The name found
        method: Similarity method (currently only 'jaccard')

    Returns:
        Similarity score (0.0-1.0)
    """
    if not query_name or not match_name:
        return 0.0

    q_lower = query_name.lower()
    m_lower = match_name.lower()

    if q_lower == m_lower:
        return 1.0

    if method == "jaccard":
        q_words = set(q_lower.split())
        m_words = set(m_lower.split())

        if not q_words or not m_words:
            return 0.0

        intersection = q_words & m_words
        union = q_words | m_words

        if not union:
            return 0.0

        return len(intersection) / len(union)

    return 0.0
