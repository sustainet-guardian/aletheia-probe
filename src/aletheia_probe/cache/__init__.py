# SPDX-License-Identifier: MIT
"""Cache module for journal data and assessment results.

This module provides a refactored cache system with focused components:
- JournalCache: Journal data management
- AcronymCache: Conference acronym mappings
- RetractionCache: Article retraction tracking
- AssessmentCache: Assessment result caching
- KeyValueCache: Generic key-value caching
- DataSourceManager: Data source management
"""

from .acronym_cache import AcronymCache
from .assessment_cache import AssessmentCache
from .data_source_manager import DataSourceManager
from .journal_cache import JournalCache
from .key_value_cache import KeyValueCache
from .retraction_cache import RetractionCache


__all__ = [
    "JournalCache",
    "AcronymCache",
    "RetractionCache",
    "AssessmentCache",
    "KeyValueCache",
    "DataSourceManager",
]
