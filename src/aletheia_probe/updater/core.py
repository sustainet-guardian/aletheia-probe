# SPDX-License-Identifier: MIT
"""Core updater classes and base abstractions."""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ..cache import (
    AssessmentCache,
    DataSourceManager,
    JournalCache,
    RetractionCache,
)
from ..cache_sync.db_writer import AsyncDBWriter
from ..data_models import JournalDataDict, JournalEntryData
from ..enums import AssessmentType, UpdateStatus, UpdateType
from ..logging_config import get_detail_logger, get_status_logger


class DataSource(ABC):
    """Abstract base class for data sources."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the source name."""
        pass

    @abstractmethod
    def get_list_type(self) -> AssessmentType:
        """Return the list type as AssessmentType enum member."""
        pass

    @abstractmethod
    async def fetch_data(self) -> list[dict[str, Any]]:
        """Fetch and parse data from the source.

        Returns:
            List of dictionaries with journal information
        """
        pass

    @abstractmethod
    def should_update(self) -> bool:
        """Check if this source needs updating."""
        pass


class UpdateSourceRegistry:
    """Registry for managing available update sources with factory-based creation."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., DataSource]] = {}
        self._default_configs: dict[str, dict[str, Any]] = {}

    def register_factory(
        self,
        name: str,
        factory: Callable[..., DataSource],
        default_config: dict[str, Any] | None = None,
    ) -> None:
        """Register an update source factory function.

        Args:
            name: Source name (must match source.get_name())
            factory: Factory function that creates source instances
            default_config: Default configuration values
        """
        self._factories[name] = factory
        self._default_configs[name] = default_config or {}

    def create_source(self, name: str, **config: Any) -> DataSource:
        """Create a source instance with configuration.

        Args:
            name: Source name
            **config: Configuration parameters to override defaults

        Returns:
            DataSource instance configured with the provided parameters
        """
        if name not in self._factories:
            raise ValueError(f"Update source '{name}' not found")

        # Merge provided config with defaults
        merged_config = {**self._default_configs[name], **config}

        # Filter config parameters based on factory signature
        factory = self._factories[name]
        filtered_config = self._filter_config_params(factory, merged_config)

        # Create source instance using factory
        return factory(**filtered_config)

    def _filter_config_params(
        self, factory: Callable[..., DataSource], config: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter config parameters based on factory function signature.

        Args:
            factory: Source factory function
            config: Configuration parameters to filter

        Returns:
            Filtered configuration with only parameters the factory accepts
        """
        try:
            sig = inspect.signature(factory)
            accepted_params = set(sig.parameters.keys())

            # Filter config to only include parameters the factory accepts
            filtered_config = {
                key: value for key, value in config.items() if key in accepted_params
            }

            return filtered_config
        except (AttributeError, ValueError, TypeError):
            # If signature inspection fails, return original config
            # This ensures backward compatibility
            return config

    def get_supported_params(self, name: str) -> set[str]:
        """Get the set of parameters supported by a source.

        Args:
            name: Source name

        Returns:
            Set of parameter names the source accepts
        """
        if name not in self._factories:
            return set()

        try:
            factory = self._factories[name]
            sig = inspect.signature(factory)
            return set(sig.parameters.keys())
        except (KeyError, AttributeError, ValueError, TypeError):
            # If signature inspection fails, return empty set
            return set()

    def get_source(self, name: str) -> DataSource:
        """Get a source by name with default configuration."""
        return self.create_source(name)

    def get_all_sources(self) -> list[DataSource]:
        """Get all registered sources with default configuration."""
        sources: list[DataSource] = []

        # Create default instances from factories
        for name in self._factories:
            try:
                sources.append(self.create_source(name))
            except (ValueError, TypeError, AttributeError, OSError):
                # Skip sources that fail to create with default config
                pass

        return sources

    def get_source_names(self) -> list[str]:
        """Get names of all registered sources."""
        return list(self._factories.keys())

    def list_all(self) -> list[DataSource]:
        """List all registered sources (alias for get_all_sources)."""
        return self.get_all_sources()


# Global update source registry with factory pattern
_update_source_registry_instance: UpdateSourceRegistry | None = None


def get_update_source_registry() -> UpdateSourceRegistry:
    """Get or create the global update source registry instance.

    Returns:
        The global UpdateSourceRegistry instance
    """
    global _update_source_registry_instance
    if _update_source_registry_instance is None:
        _update_source_registry_instance = UpdateSourceRegistry()
    return _update_source_registry_instance


def set_update_source_registry(registry: UpdateSourceRegistry) -> None:
    """Set the update source registry instance (primarily for testing).

    Args:
        registry: UpdateSourceRegistry instance to use globally
    """
    global _update_source_registry_instance
    _update_source_registry_instance = registry


def reset_update_source_registry() -> None:
    """Reset the update source registry instance (primarily for testing)."""
    global _update_source_registry_instance
    _update_source_registry_instance = None


class DataUpdater:
    """Manages updating data from multiple sources."""

    def __init__(self) -> None:
        self.sources: list[DataSource] = []

    def add_source(self, source: DataSource) -> None:
        """Add a data source."""
        self.sources.append(source)

    def get_source_by_name(self, name: str) -> DataSource | None:
        """Get a data source by name."""
        for source in self.sources:
            if source.get_name() == name:
                return source
        return None

    def add_custom_list(
        self, file_path: Path, list_type: AssessmentType, source_name: str
    ) -> None:
        """Add a custom list file as a data source."""
        from .sources.custom import CustomListSource

        source = CustomListSource(file_path, list_type, source_name)
        self.add_source(source)

    async def update_all(self, force: bool = False) -> dict[str, dict[str, Any]]:
        """Update all data sources.

        Args:
            force: Force update even if not needed

        Returns:
            Dictionary with update results for each source

        Raises:
            RuntimeError: If any sources fail to update (after all sources are attempted)
        """
        detail_logger = get_detail_logger()
        status_logger = get_status_logger()
        results = {}
        failed_sources = []

        for source in self.sources:
            result = await self.update_source(source, force)
            results[source.get_name()] = result

            # Track failures for aggregate error reporting
            if result.get("status") == "failed":
                failed_sources.append(
                    f"{source.get_name()}: {result.get('error', 'Unknown error')}"
                )

        # Clean up expired cache entries
        assessment_cache = AssessmentCache()
        assessment_expired = assessment_cache.cleanup_expired_cache()
        detail_logger.info(
            f"Cleaned up {assessment_expired} expired assessment cache entries"
        )

        retraction_cache = RetractionCache()
        retraction_expired = retraction_cache.cleanup_expired_article_retractions()
        detail_logger.info(
            f"Cleaned up {retraction_expired} expired retraction cache entries"
        )

        total_expired = assessment_expired + retraction_expired
        status_logger.info(
            f"Cache cleanup: {total_expired} total expired entries removed"
        )

        # Report all failures together
        if failed_sources:
            error_summary = f"Failed to update {len(failed_sources)} source(s):\n  - "
            error_summary += "\n  - ".join(failed_sources)
            detail_logger.error(error_summary)
            status_logger.error(
                f"Update completed with {len(failed_sources)} failure(s)"
            )
            raise RuntimeError(error_summary)

        return results

    async def update_source(
        self,
        source: DataSource,
        force: bool = False,
        db_writer: AsyncDBWriter | None = None,
    ) -> dict[str, Any]:
        """Update a specific data source."""
        source_name = source.get_name()
        status_logger = get_status_logger()
        detail_logger = get_detail_logger()
        detail_logger.info(f"Updating source: {source_name}")

        if not force and not source.should_update():
            detail_logger.info(f"Source {source_name} does not need updating")
            return {"status": "skipped", "reason": "no_update_needed"}

        start_time = datetime.now()
        data_source_manager = DataSourceManager()

        # Register data source if not already registered
        data_source_manager.register_data_source(
            name=source_name,
            display_name=source_name,
            source_type=source.get_list_type().value,
        )

        data_source_manager.log_update(
            source_name, UpdateType.FULL.value, UpdateStatus.IN_PROGRESS.value
        )

        try:
            # Fetch data from source
            status_logger.info(f"    {source_name}: Downloading...")
            journals = await source.fetch_data()

            if not journals:
                detail_logger.warning(f"No data received from source {source_name}")
                status_logger.warning(f"    {source_name}: No data received")
                data_source_manager.log_update(
                    source_name,
                    UpdateType.FULL.value,
                    UpdateStatus.FAILED.value,
                    error_message="No data received",
                )
                return {"status": "failed", "error": "No data received"}

            # Store in cache - use queue if db_writer provided, else direct writes
            if db_writer is not None:
                # Queue the data for asynchronous writing
                # Cast to JournalDataDict list - data sources return dicts that conform to this structure
                await db_writer.queue_write(
                    source_name, source.get_list_type(), cast(list[JournalDataDict], journals)
                )
                records_updated = len(journals)
                status_logger.info(
                    f"    {source_name}: Queued {records_updated} records for writing"
                )
                # Note: log_update will be called by the db_writer when actually writing
            else:
                # Fallback to direct database writes (legacy behavior)
                status_logger.info(
                    f"    {source_name}: Processing {len(journals)} records..."
                )
                records_updated = 0
                journal_cache = JournalCache()
                for journal in journals:
                    entry = JournalEntryData(
                        source_name=source_name,
                        assessment=source.get_list_type(),
                        journal_name=journal["journal_name"],
                        normalized_name=journal.get("normalized_name"),
                        issn=journal.get("issn"),
                        eissn=journal.get("eissn"),
                        publisher=journal.get("publisher"),
                        metadata=journal.get("metadata", {}),
                    )
                    journal_cache.add_journal_entry(entry)
                    records_updated += 1

                status_logger.info(f"    {source_name}: Writing to database...")

                data_source_manager.log_update(
                    source_name,
                    UpdateType.FULL.value,
                    UpdateStatus.SUCCESS.value,
                    records_updated=records_updated,
                )

            detail_logger.info(
                f"Successfully updated {source_name}: {records_updated} records"
            )
            return {
                "status": "success",
                "records_updated": records_updated,
                "processing_time": (datetime.now() - start_time).total_seconds(),
            }

        except (
            ValueError,
            OSError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            detail_logger.error(f"Failed to update source {source_name}: {e}")
            status_logger.error(f"    {source_name}: Error - {e}")
            data_source_manager.log_update(
                source_name,
                UpdateType.FULL.value,
                UpdateStatus.FAILED.value,
                error_message=str(e),
            )
            return {"status": "failed", "error": str(e)}
