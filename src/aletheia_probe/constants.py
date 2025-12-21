# SPDX-License-Identifier: MIT
"""Constants used throughout the journal assessment tool."""

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

# Retraction Watch risk levels - Rate-based thresholds (percentage)
# Research shows average retraction rate: ~0.02-0.04%
# Unified thresholds balancing different implementations
RETRACTION_RATE_CRITICAL: float = 3.0  # Very high rate
RETRACTION_RATE_HIGH: float = 1.5  # High rate
RETRACTION_RATE_MODERATE: float = 0.8  # Moderate rate
RETRACTION_RATE_LOW: float = 0.1  # Elevated rate

# Retraction Watch risk levels - Recent rate thresholds (percentage)
RETRACTION_RECENT_RATE_CRITICAL: float = 4.0
RETRACTION_RECENT_RATE_HIGH: float = 2.5
RETRACTION_RECENT_RATE_MODERATE: float = 1.2
RETRACTION_RECENT_RATE_LOW: float = 0.2

# Retraction Watch risk levels - Absolute count fallback thresholds
# These are unified thresholds balancing the different implementations
RETRACTION_COUNT_CRITICAL: int = 21
RETRACTION_COUNT_HIGH: int = 11
RETRACTION_COUNT_MODERATE: int = 6
RETRACTION_COUNT_LOW: int = 2

# Retraction Watch risk levels - Recent count fallback thresholds
RETRACTION_RECENT_COUNT_CRITICAL: int = 10
RETRACTION_RECENT_COUNT_HIGH: int = 5
RETRACTION_RECENT_COUNT_MODERATE: int = 3
RETRACTION_RECENT_COUNT_LOW: int = 2

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

# Default output format
DEFAULT_OUTPUT_FORMAT: str = "json"
