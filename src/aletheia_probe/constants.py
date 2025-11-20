# SPDX-License-Identifier: MIT
"""Constants used throughout the journal assessment tool."""

# Assessment confidence thresholds
CONFIDENCE_THRESHOLD_HIGH = 0.98
CONFIDENCE_THRESHOLD_MEDIUM = 0.85
CONFIDENCE_THRESHOLD_LOW = 0.70

# Agreement bonuses
AGREEMENT_BONUS_THRESHOLD = 0.85
AGREEMENT_BONUS_AMOUNT = 0.05

# OpenAlex pattern analysis
CITATION_RATIO_SUSPICIOUS = 10
GROWTH_RATE_THRESHOLD = 0.5
MIN_PUBLICATION_VOLUME = 100
MAX_AUTHOR_DIVERSITY = 0.95

# Crossref metadata quality
MIN_ABSTRACT_LENGTH = 50
MIN_REFERENCE_COUNT = 10
MIN_AUTHOR_INFO_COMPLETENESS = 0.8

# Retraction Watch risk levels - Rate-based thresholds (percentage)
# Research shows average retraction rate: ~0.02-0.04%
# Unified thresholds balancing different implementations
RETRACTION_RATE_CRITICAL = 3.0  # Very high rate
RETRACTION_RATE_HIGH = 1.5  # High rate
RETRACTION_RATE_MODERATE = 0.8  # Moderate rate
RETRACTION_RATE_LOW = 0.1  # Elevated rate

# Retraction Watch risk levels - Recent rate thresholds (percentage)
RETRACTION_RECENT_RATE_CRITICAL = 4.0
RETRACTION_RECENT_RATE_HIGH = 2.5
RETRACTION_RECENT_RATE_MODERATE = 1.2
RETRACTION_RECENT_RATE_LOW = 0.2

# Retraction Watch risk levels - Absolute count fallback thresholds
# These are unified thresholds balancing the different implementations
RETRACTION_COUNT_CRITICAL = 21
RETRACTION_COUNT_HIGH = 11
RETRACTION_COUNT_MODERATE = 6
RETRACTION_COUNT_LOW = 2

# Retraction Watch risk levels - Recent count fallback thresholds
RETRACTION_RECENT_COUNT_CRITICAL = 10
RETRACTION_RECENT_COUNT_HIGH = 5
RETRACTION_RECENT_COUNT_MODERATE = 3
RETRACTION_RECENT_COUNT_LOW = 2

# Cache TTL (seconds)
ASSESSMENT_CACHE_TTL = 86400  # 24 hours
API_CACHE_TTL = 604800  # 7 days

# API rate limits (requests per second)
DOAJ_REQUESTS_PER_SECOND = 10
OPENALEX_REQUESTS_PER_SECOND = 10
CROSSREF_REQUESTS_PER_SECOND = 50

# Default configuration values
# Default backend configuration
DEFAULT_BACKEND_WEIGHT = 0.8
DEFAULT_BACKEND_TIMEOUT = 10

# Default heuristic thresholds
DEFAULT_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_UNKNOWN_THRESHOLD = 0.3
DEFAULT_BACKEND_AGREEMENT_BONUS = 0.2

# Default cache settings
DEFAULT_CACHE_UPDATE_THRESHOLD_DAYS = 7

# Default output format
DEFAULT_OUTPUT_FORMAT = "json"
