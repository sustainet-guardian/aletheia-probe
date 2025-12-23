# SPDX-License-Identifier: MIT
"""Cache module for journal data and assessment results.

This module provides a refactored cache system with focused components:
- CacheManager: Main facade for all caching operations
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
from .manager import CacheManager
from .retraction_cache import RetractionCache


# Global cache manager instance with factory pattern
_cache_manager_instance: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance.

    Returns:
        The global CacheManager instance
    """
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = CacheManager()
    return _cache_manager_instance


def set_cache_manager(manager: CacheManager) -> None:
    """Set the cache manager instance (primarily for testing).

    Args:
        manager: CacheManager instance to use globally
    """
    global _cache_manager_instance
    _cache_manager_instance = manager


def reset_cache_manager() -> None:
    """Reset the cache manager instance (primarily for testing)."""
    global _cache_manager_instance
    _cache_manager_instance = None


__all__ = [
    "CacheManager",
    "JournalCache",
    "AcronymCache",
    "RetractionCache",
    "AssessmentCache",
    "KeyValueCache",
    "DataSourceManager",
    "get_cache_manager",
    "set_cache_manager",
    "reset_cache_manager",
]
