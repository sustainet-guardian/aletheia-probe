# SPDX-License-Identifier: MIT
"""Core updater classes and base abstractions."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from ..cache import get_cache_manager
from ..logging_config import get_detail_logger, get_status_logger


class DataSource(ABC):
    """Abstract base class for data sources."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the source name."""
        pass

    @abstractmethod
    def get_list_type(self) -> str:
        """Return the list type: 'predatory', 'legitimate', or 'unknown'."""
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
        self, file_path: Path, list_type: str, source_name: str
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
        """
        detail_logger = get_detail_logger()
        results = {}

        for source in self.sources:
            result = await self.update_source(source, force)
            results[source.get_name()] = result

        # Clean up expired cache entries
        expired_count = get_cache_manager().cleanup_expired_cache()
        detail_logger.info(f"Cleaned up {expired_count} expired cache entries")

        return results

    async def update_source(
        self, source: DataSource, force: bool = False, db_writer: Any = None
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
        get_cache_manager().log_update(source_name, "full", "started")

        try:
            # Fetch data from source
            status_logger.info(f"    {source_name}: Downloading...")
            journals = await source.fetch_data()

            if not journals:
                detail_logger.warning(f"No data received from source {source_name}")
                status_logger.warning(f"    {source_name}: No data received")
                get_cache_manager().log_update(
                    source_name, "full", "failed", error_message="No data received"
                )
                return {"status": "failed", "error": "No data received"}

            # Store in cache - use queue if db_writer provided, else direct writes
            if db_writer is not None:
                # Queue the data for asynchronous writing
                await db_writer.queue_write(
                    source_name, source.get_list_type(), journals
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
                for journal in journals:
                    get_cache_manager().add_journal_list_entry(
                        source_name=source_name,
                        list_type=source.get_list_type(),
                        journal_name=journal["journal_name"],
                        normalized_name=journal.get("normalized_name"),
                        issn=journal.get("issn"),
                        eissn=journal.get("eissn"),
                        publisher=journal.get("publisher"),
                        metadata=journal.get("metadata"),
                    )
                    records_updated += 1

                status_logger.info(f"    {source_name}: Writing to database...")

                get_cache_manager().log_update(
                    source_name, "full", "success", records_updated=records_updated
                )

            detail_logger.info(
                f"Successfully updated {source_name}: {records_updated} records"
            )
            return {
                "status": "success",
                "records_updated": records_updated,
                "processing_time": (datetime.now() - start_time).total_seconds(),
            }

        except Exception as e:
            detail_logger.error(f"Failed to update source {source_name}: {e}")
            status_logger.error(f"    {source_name}: Error - {e}")
            get_cache_manager().log_update(
                source_name, "full", "failed", error_message=str(e)
            )
            return {"status": "failed", "error": str(e)}
