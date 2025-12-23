# SPDX-License-Identifier: MIT
"""Main cache manager that composes all cache components."""

from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import AssessmentResult
from .acronym_cache import AcronymCache
from .assessment_cache import AssessmentCache
from .data_source_manager import DataSourceManager
from .journal_cache import JournalCache
from .key_value_cache import KeyValueCache
from .retraction_cache import RetractionCache
from .schema import init_database


class CacheManager:
    """Manages SQLite-based normalized caching for journal data and assessment results.

    This is a facade that composes specialized cache components.
    """

    def __init__(self, db_path: Path | None = None):
        """Initialize cache manager with database path.

        Args:
            db_path: Path to the SQLite database file. If None, uses default location.
        """
        if db_path is None:
            # Default to local project directory for paper-specific assessment data
            local_dir = Path.cwd() / ".aletheia-probe"
            local_dir.mkdir(exist_ok=True)
            self.db_path = local_dir / "cache.db"
        else:
            # Ensure db_path is always a Path object
            self.db_path = Path(db_path)

        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        init_database(self.db_path)

        # Initialize component caches
        self._journal_cache = JournalCache(self.db_path)
        self._acronym_cache = AcronymCache(self.db_path)
        self._retraction_cache = RetractionCache(self.db_path)
        self._assessment_cache = AssessmentCache(self.db_path)
        self._key_value_cache = KeyValueCache(self.db_path)
        self._data_source_manager = DataSourceManager(self.db_path)

    # Delegate to DataSourceManager
    def register_data_source(
        self,
        name: str,
        display_name: str,
        source_type: str,
        authority_level: int = 5,
        base_url: str | None = None,
        description: str | None = None,
    ) -> int:
        """Register a data source and return its ID."""
        return self._data_source_manager.register_data_source(
            name, display_name, source_type, authority_level, base_url, description
        )

    def get_source_statistics(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all data sources."""
        return self._data_source_manager.get_source_statistics()

    def get_source_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all data sources in structured format."""
        return self._data_source_manager.get_source_stats()

    def find_conflicts(self) -> list[dict[str, Any]]:
        """Find journals with conflicting assessments from different sources."""
        return self._data_source_manager.find_conflicts()

    def log_update(
        self,
        source_name: str,
        update_type: str,
        status: str,
        records_added: int = 0,
        records_updated: int = 0,
        records_removed: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Log a source update operation."""
        self._data_source_manager.log_update(
            source_name,
            update_type,
            status,
            records_added,
            records_updated,
            records_removed,
            error_message,
        )

    def get_source_last_updated(self, source_name: str) -> datetime | None:
        """Get the last successful update time for a source."""
        return self._data_source_manager.get_source_last_updated(source_name)

    def has_source_data(self, source_name: str) -> bool:
        """Check if a data source has any journal entries."""
        return self._data_source_manager.has_source_data(source_name)

    def remove_source_data(self, source_name: str) -> int:
        """Remove all data for a specific source."""
        return self._data_source_manager.remove_source_data(source_name)

    def get_available_sources(self) -> list[str]:
        """Get list of all available data sources."""
        return self._data_source_manager.get_available_sources()

    # Delegate to JournalCache
    def add_journal_entry(self, **kwargs: Any) -> int:
        """Add or update a journal entry with normalized deduplication."""
        return self._journal_cache.add_journal_entry(**kwargs)

    def search_journals_by_name(
        self, name: str, source_name: str, assessment: str
    ) -> list[dict[str, Any]]:
        """Search for journals by exact normalized name match."""
        return self._journal_cache.search_journals_by_name(
            name, source_name, assessment
        )

    def search_journals(
        self,
        normalized_name: str | None = None,
        journal_name: str | None = None,
        issn: str | None = None,
        source_name: str | None = None,
        assessment: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for journals with normalized results."""
        return self._journal_cache.search_journals(
            normalized_name, journal_name, issn, source_name, assessment
        )

    def add_journal_list_entry(
        self,
        source_name: str,
        list_type: str,
        journal_name: str,
        normalized_name: str | None = None,
        issn: str | None = None,
        eissn: str | None = None,
        publisher: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a journal entry using list-based nomenclature."""
        self._journal_cache.add_journal_list_entry(
            source_name,
            list_type,
            journal_name,
            normalized_name,
            issn,
            eissn,
            publisher,
            metadata,
        )

    # Delegate to AcronymCache
    def get_full_name_for_acronym(self, acronym: str) -> str | None:
        """Look up the normalized name for a conference/journal acronym."""
        return self._acronym_cache.get_full_name_for_acronym(acronym)

    def store_acronym_mapping(
        self, acronym: str, full_name: str, source: str = "unknown"
    ) -> None:
        """Store an acronym to normalized name mapping in the cache."""
        self._acronym_cache.store_acronym_mapping(acronym, full_name, source)

    def get_acronym_stats(self) -> dict[str, int | str]:
        """Get statistics about the acronym database."""
        return self._acronym_cache.get_acronym_stats()

    def list_all_acronyms(
        self, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, str]]:
        """List all acronym mappings in the database."""
        return self._acronym_cache.list_all_acronyms(limit, offset)

    def clear_acronym_database(self) -> int:
        """Clear all entries from the acronym database."""
        return self._acronym_cache.clear_acronym_database()

    # Delegate to RetractionCache
    def get_article_retraction(self, doi: str) -> dict[str, Any] | None:
        """Get cached retraction information for a DOI."""
        return self._retraction_cache.get_article_retraction(doi)

    def cache_article_retraction(self, **kwargs: Any) -> None:
        """Cache retraction information for a DOI."""
        self._retraction_cache.cache_article_retraction(**kwargs)

    def cleanup_expired_article_retractions(self) -> int:
        """Remove expired article retraction cache entries."""
        return self._retraction_cache.cleanup_expired_article_retractions()

    # Delegate to AssessmentCache
    def cache_assessment_result(
        self,
        query_hash: str,
        query_input: str,
        result: AssessmentResult,
        ttl_hours: int = 24,
    ) -> None:
        """Cache an assessment result with TTL."""
        self._assessment_cache.cache_assessment_result(
            query_hash, query_input, result, ttl_hours
        )

    def get_cached_assessment(self, query_hash: str) -> AssessmentResult | None:
        """Get cached assessment result if not expired."""
        return self._assessment_cache.get_cached_assessment(query_hash)

    def cleanup_expired_cache(self) -> int:
        """Remove expired assessment cache entries."""
        return self._assessment_cache.cleanup_expired_cache()

    def get_assessment_cache_count(self) -> int:
        """Get the count of assessment cache entries."""
        return self._assessment_cache.get_assessment_cache_count()

    def clear_assessment_cache(self) -> int:
        """Clear all assessment cache entries."""
        return self._assessment_cache.clear_assessment_cache()

    # Delegate to KeyValueCache
    def set_cached_value(self, key: str, value: str, ttl_hours: int = 24) -> None:
        """Store a key-value pair in cache with TTL."""
        self._key_value_cache.set_cached_value(key, value, ttl_hours)

    def get_cached_value(self, key: str) -> str | None:
        """Get a cached value by key."""
        return self._key_value_cache.get_cached_value(key)

    # Expose normalization utility from base
    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize text for robust comparison."""
        return self._journal_cache._normalize_for_comparison(text)
