# SPDX-License-Identifier: MIT
"""Constants for shared configuration used across the journal assessment tool.

This module contains configuration constants that are used by multiple modules:

- **Assessment thresholds**: Confidence levels and agreement bonuses for quality scoring
- **Default configurations**: Fallback values for backend weights, timeouts, cache settings, and output formats

Domain-specific constants are co-located with their implementations:
- Normalization constants → normalizer.py
- OpenAlex analysis constants → backends/openalex_analyzer.py
- Retraction risk thresholds → risk_calculator.py
"""

# Assessment confidence thresholds
CONFIDENCE_THRESHOLD_HIGH: float = 0.98
CONFIDENCE_THRESHOLD_MEDIUM: float = 0.85
CONFIDENCE_THRESHOLD_LOW: float = 0.3

# Agreement bonuses
AGREEMENT_BONUS_AMOUNT: float = 0.05

# Cache database path
DEFAULT_CACHE_DB_PATH: str = ".aletheia-probe/cache.db"  # Relative to current directory

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
