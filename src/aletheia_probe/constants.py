# SPDX-License-Identifier: MIT
"""Constants used throughout the journal assessment tool.

This module centralizes all configuration constants including:

- **Assessment thresholds**: Confidence levels and agreement bonuses for quality scoring
- **Pattern analysis limits**: Citation ratios, growth rates, and metadata quality standards
- **Retraction risk thresholds**: Research-based values (avg. rate: 0.02-0.04%) for identifying
  journals with concerning retraction patterns
- **Cache settings**: TTL values for assessment and API response caching
- **API rate limits**: Respectful request rates for external data sources (DOAJ, OpenAlex, Crossref)
- **Default configurations**: Fallback values for backend weights, timeouts, and output formats
"""

from dataclasses import dataclass


# Assessment confidence thresholds
CONFIDENCE_THRESHOLD_HIGH: float = 0.98
CONFIDENCE_THRESHOLD_MEDIUM: float = 0.85
CONFIDENCE_THRESHOLD_LOW: float = 0.70

# Agreement bonuses
AGREEMENT_BONUS_THRESHOLD: float = 0.85
AGREEMENT_BONUS_AMOUNT: float = 0.05

# OpenAlex pattern analysis
CITATION_RATIO_SUSPICIOUS: int = 10
GROWTH_RATE_THRESHOLD: float = 0.5
MIN_PUBLICATION_VOLUME: int = 100
MAX_AUTHOR_DIVERSITY: float = 0.95

# Crossref metadata quality
MIN_ABSTRACT_LENGTH: int = 50
MIN_REFERENCE_COUNT: int = 10
MIN_AUTHOR_INFO_COMPLETENESS: float = 0.8


@dataclass(frozen=True)
class RetractionThresholds:
    """Thresholds for assessing retraction risk levels.

    Research shows average retraction rate: ~0.02-0.04%
    Unified thresholds balancing different implementations.
    """

    # Rate-based thresholds (percentage)
    rate_critical: float = 3.0  # Very high rate
    rate_high: float = 1.5  # High rate
    rate_moderate: float = 0.8  # Moderate rate
    rate_low: float = 0.1  # Elevated rate

    # Recent rate thresholds (percentage)
    recent_rate_critical: float = 4.0
    recent_rate_high: float = 2.5
    recent_rate_moderate: float = 1.2
    recent_rate_low: float = 0.2

    # Absolute count fallback thresholds
    count_critical: int = 21
    count_high: int = 11
    count_moderate: int = 6
    count_low: int = 2

    # Recent count fallback thresholds
    recent_count_critical: int = 10
    recent_count_high: int = 5
    recent_count_moderate: int = 3
    recent_count_low: int = 2


# Instance for use throughout the application
RETRACTION_THRESHOLDS = RetractionThresholds()

# Cache TTL (seconds)
ASSESSMENT_CACHE_TTL: int = 86400  # 24 hours
API_CACHE_TTL: int = 604800  # 7 days

# API rate limits (requests per second)
DOAJ_REQUESTS_PER_SECOND: int = 10
OPENALEX_REQUESTS_PER_SECOND: int = 10
CROSSREF_REQUESTS_PER_SECOND: int = 50

# Default configuration values
# Default backend configuration
DEFAULT_BACKEND_WEIGHT: float = 0.8
DEFAULT_BACKEND_TIMEOUT: int = 10

# Default heuristic thresholds
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6
DEFAULT_UNKNOWN_THRESHOLD: float = 0.3
DEFAULT_BACKEND_AGREEMENT_BONUS: float = 0.2

# Default cache settings
DEFAULT_CACHE_UPDATE_THRESHOLD_DAYS: int = 7
DEFAULT_CACHE_AUTO_SYNC: bool = True

# Default output format
DEFAULT_OUTPUT_FORMAT: str = "json"
