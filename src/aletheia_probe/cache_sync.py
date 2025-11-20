# SPDX-License-Identifier: MIT
"""Cache synchronization manager for automatic backend data management."""

import asyncio
from datetime import datetime
from typing import Any

from .backends.base import Backend, CachedBackend, HybridBackend, get_backend_registry
from .cache import get_cache_manager
from .config import get_config_manager
from .enums import UpdateStatus
from .logging_config import get_detail_logger, get_status_logger
from .updater import data_updater  # Global updater instance from updater package


class AsyncDBWriter:
    """Handles database writes asynchronously to prevent blocking."""

    def __init__(self) -> None:
        self.write_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.writer_task: asyncio.Task[None] | None = None
        self.status_logger = get_status_logger()

    async def start_writer(self) -> None:
        """Start the database writer task."""
        if self.writer_task is None:
            self.status_logger.info("    DBWriter: Starting database writer task...")
            self.writer_task = asyncio.create_task(self._db_writer_loop())

    async def stop_writer(self) -> None:
        """Stop the database writer task."""
        if self.writer_task:
            self.status_logger.info("    DBWriter: Stopping database writer task...")
            await self.write_queue.put(None)  # Signal to stop
            await self.writer_task
            self.writer_task = None
            self.status_logger.info("    DBWriter: Database writer task stopped")

    async def queue_write(
        self, source_name: str, list_type: str, journals: list[dict[str, Any]]
    ) -> None:
        """Queue data for database writing."""
        self.status_logger.info(
            f"    DBWriter: Received {len(journals)} records from {source_name} for queuing"
        )
        await self.write_queue.put(
            {"source_name": source_name, "list_type": list_type, "journals": journals}
        )
        self.status_logger.info(
            f"    DBWriter: Queued {len(journals)} records from {source_name}"
        )

    async def _db_writer_loop(self) -> None:
        """Main database writer loop - processes write queue sequentially."""
        while True:
            try:
                write_data = await self.write_queue.get()

                # None signals shutdown
                if write_data is None:
                    break

                source_name = write_data["source_name"]
                list_type = write_data["list_type"]
                journals = write_data["journals"]

                self.status_logger.info(
                    f"    DBWriter: Processing {source_name} - Writing {len(journals)} records to database..."
                )

                # Perform optimized batch database writes
                write_result = self._batch_write_journals(
                    source_name, list_type, journals
                )

                total_records = write_result["total_records"]
                unique_journals = write_result["unique_journals"]
                duplicates = write_result["duplicates"]

                get_cache_manager().log_update(
                    source_name, "full", "success", records_updated=total_records
                )

                if duplicates > 0:
                    self.status_logger.info(
                        f"    DBWriter: Completed {source_name} - {total_records} records → "
                        f"{unique_journals} unique journals ({duplicates} duplicates merged)"
                    )
                else:
                    self.status_logger.info(
                        f"    DBWriter: Completed {source_name} - {unique_journals} unique journals"
                    )

            except Exception as e:
                self.status_logger.error(f"Database write error: {e}")

    def _batch_write_journals(
        self, source_name: str, list_type: str, journals: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Optimized batch writing of journals to database using SQLite performance tuning."""
        import json
        import sqlite3

        cache_manager = get_cache_manager()

        # Get database connection with performance optimizations
        with sqlite3.connect(cache_manager.db_path) as conn:
            # SQLite performance optimizations
            conn.execute(
                "PRAGMA journal_mode = WAL"
            )  # Write-ahead logging for better concurrency
            conn.execute("PRAGMA synchronous = NORMAL")  # Faster writes, still safe
            conn.execute("PRAGMA cache_size = 10000")  # Increase cache size
            conn.execute("PRAGMA temp_store = MEMORY")  # Store temp data in memory

            cursor = conn.cursor()

            # Ensure source is registered
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            source_row = cursor.fetchone()
            if not source_row:
                cache_manager.register_data_source(source_name, source_name, "mixed")
                cursor.execute(
                    "SELECT id FROM data_sources WHERE name = ?", (source_name,)
                )
                source_row = cursor.fetchone()
            source_id = source_row[0]

            # Begin explicit transaction for batch operations
            conn.execute("BEGIN TRANSACTION")

            try:
                records_updated = 0
                total_input_records = 0
                unique_journals = 0

                # Prepare all data for batch operations
                name_inserts = []
                assessment_inserts = []
                metadata_inserts = []

                # First, collect all normalized names that will be processed
                normalized_names = [
                    j.get("normalized_name")
                    for j in journals
                    if j.get("normalized_name")
                ]

                # Track unique normalized names to count duplicates
                unique_normalized_names = set()

                # Use INSERT OR REPLACE for all journals to handle both new and existing entries
                journal_upserts = []
                for journal in journals:
                    normalized_name = journal.get("normalized_name")
                    if not normalized_name:
                        continue

                    total_input_records += 1
                    unique_normalized_names.add(normalized_name)

                    journal_name = journal["journal_name"]
                    issn = journal.get("issn")
                    eissn = journal.get("eissn")
                    publisher = journal.get("publisher")

                    journal_upserts.append(
                        (normalized_name, journal_name, issn, eissn, publisher)
                    )
                    records_updated += 1

                unique_journals = len(unique_normalized_names)

                # Batch upsert all journals using INSERT OR REPLACE
                if journal_upserts:
                    cursor.executemany(
                        """INSERT OR REPLACE INTO journals (normalized_name, display_name, issn, eissn, publisher)
                           VALUES (?, ?, ?, ?, ?)""",
                        journal_upserts,
                    )

                # Get all journal IDs for the processed journals
                existing_journals = {}
                if normalized_names:
                    placeholders = ",".join("?" * len(normalized_names))
                    cursor.execute(
                        f"SELECT id, normalized_name FROM journals WHERE normalized_name IN ({placeholders})",  # nosec B608
                        normalized_names,
                    )
                    existing_journals = {row[1]: row[0] for row in cursor.fetchall()}

                # Prepare batch data for related tables
                for journal in journals:
                    normalized_name = journal.get("normalized_name")
                    if not normalized_name or normalized_name not in existing_journals:
                        continue

                    journal_id = existing_journals[normalized_name]
                    journal_name = journal["journal_name"]
                    metadata = journal.get("metadata")

                    # Journal names
                    name_inserts.append(
                        (journal_id, journal_name, "canonical", source_name)
                    )

                    # Source assessments
                    assessment_inserts.append((journal_id, source_id, list_type, 1.0))

                    # Metadata
                    if metadata:
                        for key, value in metadata.items():
                            if value is not None:
                                data_type = "string"
                                if isinstance(value, bool):
                                    data_type = "boolean"
                                    value = str(value).lower()
                                elif isinstance(value, int):
                                    data_type = "integer"
                                    value = str(value)
                                elif isinstance(value, (dict, list)):
                                    data_type = "json"
                                    value = json.dumps(value)
                                else:
                                    value = str(value)
                                metadata_inserts.append(
                                    (journal_id, source_id, key, value, data_type)
                                )

                # Batch insert journal names
                if name_inserts:
                    cursor.executemany(
                        """INSERT OR IGNORE INTO journal_names
                           (journal_id, name, name_type, source_name)
                           VALUES (?, ?, ?, ?)""",
                        name_inserts,
                    )

                # Batch insert/update source assessments
                if assessment_inserts:
                    cursor.executemany(
                        """INSERT OR REPLACE INTO source_assessments
                           (journal_id, source_id, assessment, confidence, last_confirmed_at)
                           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        assessment_inserts,
                    )

                # Batch insert/update metadata
                if metadata_inserts:
                    cursor.executemany(
                        """INSERT OR REPLACE INTO source_metadata
                           (journal_id, source_id, metadata_key, metadata_value, data_type)
                           VALUES (?, ?, ?, ?, ?)""",
                        metadata_inserts,
                    )

                # Commit transaction
                conn.execute("COMMIT")

                return {
                    "total_records": total_input_records,
                    "unique_journals": unique_journals,
                    "duplicates": total_input_records - unique_journals,
                }

            except Exception as e:
                conn.execute("ROLLBACK")
                self.status_logger.error(f"Batch write error: {e}")
                raise


class CacheSyncManager:
    """Manages automatic synchronization of cache data based on backend configuration."""

    # Maximum number of backends to sync concurrently
    MAX_CONCURRENT_SOURCES = 999

    def __init__(self) -> None:
        self.sync_in_progress = False
        self.config_manager = get_config_manager()
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()
        self.db_writer = AsyncDBWriter()

    async def sync_cache_with_config(
        self,
        force: bool = False,
        backend_filter: list[str] | None = None,
        show_progress: bool = True,
    ) -> dict[str, str | dict[str, Any]]:
        """Sync cache state with enabled/disabled backends.

        Args:
            force: Force update even if data appears fresh
            backend_filter: Optional list of backend names to sync. If None, syncs all backends.
            show_progress: Show progress output to console. Defaults to True.

        Returns:
            Dictionary with sync results for each backend
        """
        if self.sync_in_progress:
            self.detail_logger.info("Cache sync already in progress, skipping")
            self.status_logger.warning("Cache sync already in progress")
            return {"status": UpdateStatus.SKIPPED.value, "reason": "sync_in_progress"}

        try:
            self.sync_in_progress = True

            # Start the database writer
            await self.db_writer.start_writer()

            self.detail_logger.info(
                "Starting cache synchronization with backend configuration"
            )
            if show_progress:
                self.status_logger.info(
                    "Synchronizing cache with backend configuration..."
                )

            # Get configuration settings
            config = self.config_manager.load_config()
            cache_config = getattr(config, "cache", None)
            auto_sync = (
                getattr(cache_config, "auto_sync", True) if cache_config else True
            )
            cleanup_disabled = (
                getattr(cache_config, "cleanup_disabled", True)
                if cache_config
                else True
            )

            if not auto_sync and not force:
                self.detail_logger.info("Auto sync disabled in configuration")
                if show_progress:
                    self.status_logger.info("Auto sync disabled in configuration")
                return {
                    "status": UpdateStatus.SKIPPED.value,
                    "reason": "auto_sync_disabled",
                }

            sync_results: dict[str, str | dict[str, Any]] = {}

            # Get all registered backends and their enabled status
            backend_registry = get_backend_registry()
            all_backend_names = backend_registry.get_backend_names()
            enabled_backend_names = self.config_manager.get_enabled_backends()

            # Apply backend filter if provided
            if backend_filter:
                backends_to_sync = [
                    name for name in all_backend_names if name in backend_filter
                ]
                if not backends_to_sync:
                    self.detail_logger.warning(
                        f"No matching backends found for filter: {backend_filter}"
                    )
                    self.status_logger.warning(
                        f"No matching backends found for filter: {backend_filter}"
                    )
                    return {"status": "error", "error": "No matching backends found"}
                self.detail_logger.info(f"Syncing only: {', '.join(backends_to_sync)}")
                if show_progress:
                    self.status_logger.info(
                        f"Syncing backends: {', '.join(backends_to_sync)}"
                    )
            else:
                backends_to_sync = all_backend_names
                self.detail_logger.debug(
                    f"Syncing all backends: {', '.join(backends_to_sync)}"
                )

            # Filter to only backends that actually need processing:
            # - CachedBackend or HybridBackend types (need data syncing)
            # - OR disabled backends that need cleanup
            backends_needing_sync = []
            for backend_name in backends_to_sync:
                try:
                    backend = backend_registry.get_backend(backend_name)
                    is_cached = isinstance(backend, (CachedBackend, HybridBackend))
                    is_disabled = backend_name not in enabled_backend_names

                    if is_cached or (is_disabled and cleanup_disabled):
                        backends_needing_sync.append(backend_name)
                    else:
                        # Skip non-cached backends that don't need cleanup
                        sync_results[backend_name] = {
                            "status": "skipped",
                            "reason": "not_cached_backend",
                        }
                except Exception as e:
                    # If we can't get the backend, mark as error and skip
                    self.detail_logger.exception(
                        f"Error getting backend {backend_name}: {e}"
                    )
                    sync_results[backend_name] = {
                        "status": "error",
                        "error": str(e),
                        "type": type(e).__name__,
                    }
                    if show_progress:
                        self.status_logger.error(
                            f"  {backend_name}: {type(e).__name__} - {e}"
                        )

            self.detail_logger.debug(
                f"Backends needing sync: {', '.join(backends_needing_sync)}"
            )

            # Create semaphore to limit concurrent backend syncs
            semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SOURCES)

            # Process all backends with controlled concurrency (3 at a time)
            self.detail_logger.debug(
                f"Starting {len(backends_needing_sync)} backends concurrently: {backends_needing_sync}"
            )

            # Use moderate concurrency with proper semaphore control
            max_concurrent = 5
            semaphore = asyncio.Semaphore(max_concurrent)
            self.status_logger.info(
                f"Using {max_concurrent} concurrent backends with proper semaphore control"
            )

            tasks = [
                self._process_backend_with_semaphore(
                    backend_name,
                    enabled_backend_names,
                    cleanup_disabled,
                    force,
                    show_progress,
                    semaphore,
                )
                for backend_name in backends_needing_sync
            ]

            # Execute all tasks concurrently with controlled semaphore
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update sync_results
            for backend_name, result in zip(
                backends_needing_sync, results, strict=True
            ):
                if isinstance(result, BaseException):
                    # Handle exceptions returned from gather
                    self.detail_logger.exception(
                        f"Unexpected error syncing backend {backend_name}: {result}"
                    )
                    sync_results[backend_name] = {
                        "status": "error",
                        "error": str(result),
                        "type": type(result).__name__,
                    }
                    if show_progress:
                        self.status_logger.error(
                            f"  {backend_name}: {type(result).__name__} - {result}"
                        )
                else:
                    # Type narrowing: result is dict[str, str | int] here
                    sync_results[backend_name] = result

                    # Log status after completion
                    if show_progress:
                        result_value = sync_results[backend_name]
                        if isinstance(result_value, dict):
                            status = result_value.get("status", "unknown")
                            if status == UpdateStatus.SUCCESS:
                                count = result_value.get("records_updated", 0)
                                self.status_logger.info(
                                    f"  {backend_name}: Updated {count} records"
                                )
                            elif status == "current":
                                self.status_logger.info(
                                    f"  {backend_name}: Data is current"
                                )
                            elif status == "cleaned":
                                count = result_value.get("records_removed", 0)
                                self.status_logger.info(
                                    f"  {backend_name}: Cleaned {count} records (disabled)"
                                )
                            elif status == "skipped":
                                reason = result_value.get("reason", "")
                                self.status_logger.info(
                                    f"  {backend_name}: Skipped ({reason})"
                                )
                            elif status == "failed":
                                self.status_logger.warning(f"  {backend_name}: Failed")
                            elif status == "error":
                                error = result_value.get("error", "unknown error")
                                self.status_logger.error(
                                    f"  {backend_name}: Error - {error}"
                                )
                            else:
                                self.status_logger.info(f"  {backend_name}: {status}")
                        elif isinstance(result_value, str):
                            self.status_logger.info(f"  {backend_name}: {result_value}")

            self.detail_logger.info(
                f"Cache synchronization completed. Results: {sync_results}"
            )
            if show_progress:
                self.status_logger.info("Synchronization completed")
            return sync_results

        finally:
            # Stop the database writer
            await self.db_writer.stop_writer()
            self.sync_in_progress = False

    async def _process_backend_with_semaphore(
        self,
        backend_name: str,
        enabled_backend_names: list[str],
        cleanup_disabled: bool,
        force: bool,
        show_progress: bool,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, str | int]:
        """Process a single backend with semaphore-controlled concurrency.

        Args:
            backend_name: Name of the backend to process
            enabled_backend_names: List of enabled backend names
            cleanup_disabled: Whether to cleanup disabled backends
            force: Force update even if data appears fresh
            show_progress: Show progress output to console
            semaphore: Semaphore to limit concurrent operations

        Returns:
            Dictionary with operation result
        """
        # Get backend first
        backend_registry = get_backend_registry()
        backend = backend_registry.get_backend(backend_name)
        self.detail_logger.debug(f"Processing backend: {backend_name}")

        # Handle disabled backends quickly (no concurrency limit needed)
        if backend_name not in enabled_backend_names:
            if cleanup_disabled:
                try:
                    result = await self._cleanup_disabled_backend_data(
                        backend, show_progress
                    )
                    return result
                except Exception as e:
                    self.detail_logger.exception(
                        f"Error cleaning up {backend_name}: {e}"
                    )
                    return {"status": "error", "error": str(e)}
            else:
                self.detail_logger.debug(f"{backend_name}: Skipped (cleanup disabled)")
                return {
                    "status": UpdateStatus.SKIPPED.value,
                    "reason": "cleanup_disabled",
                }

        # Use semaphore to limit concurrent network operations
        async with semaphore:
            # Show start message only after acquiring semaphore slot
            if isinstance(backend, CachedBackend) and show_progress:
                self.status_logger.info(f"  {backend_name}: Starting sync...")
            try:
                result = await self._ensure_backend_data_available(
                    backend, force, show_progress
                )
                return result
            except ConnectionError as e:
                error_msg = (
                    f"Connection error syncing backend {backend_name}: {e}. "
                    "This may be temporary."
                )
                self.detail_logger.warning(error_msg)
                if show_progress:
                    self.status_logger.error(
                        f"  {backend_name}: Connection error - {e}"
                    )
                return {
                    "status": UpdateStatus.ERROR.value,
                    "error": str(e),
                }
            except TimeoutError as e:
                error_msg = (
                    f"Timeout error syncing backend {backend_name}: {e}. "
                    "Service may be slow or unavailable."
                )
                self.detail_logger.warning(error_msg)
                if show_progress:
                    self.status_logger.error(f"  {backend_name}: Timeout - {e}")
                return {
                    "status": UpdateStatus.ERROR.value,
                    "error": str(e),
                }
            except ValueError as e:
                error_msg = f"Data validation error in {backend_name}: {e}. Skipping."
                self.detail_logger.error(error_msg)
                if show_progress:
                    self.status_logger.error(
                        f"  {backend_name}: Validation error - {e}"
                    )
                return {
                    "status": UpdateStatus.ERROR.value,
                    "error": str(e),
                }
            except Exception as e:
                self.detail_logger.exception(
                    f"Unexpected error syncing backend {backend_name}: {e}"
                )
                if show_progress:
                    self.status_logger.error(
                        f"  {backend_name}: {type(e).__name__} - {e}"
                    )
                return {
                    "status": "error",
                    "error": str(e),
                    "type": type(e).__name__,
                }

    async def _ensure_backend_data_available(
        self, backend: Backend, force: bool = False, show_progress: bool = True
    ) -> dict[str, str | int]:
        """Ensure data is available for an enabled backend.

        Args:
            backend: Backend instance
            force: Force update even if data appears fresh
            show_progress: Show progress output to console

        Returns:
            Dictionary with operation result
        """
        backend_name = backend.get_name()

        # Only handle CachedBackend types (bealls, algerian_ministry)
        if not isinstance(backend, CachedBackend):
            self.detail_logger.debug(f"{backend_name}: Skipped (not a cached backend)")
            return {"status": "skipped", "reason": "not_cached_backend"}

        source_name = backend.source_name

        # Check if data exists
        has_data = get_cache_manager().has_source_data(source_name)

        if not has_data:
            self.detail_logger.info(
                f"No data found for enabled backend {backend_name}, fetching..."
            )
            return await self._fetch_backend_data(source_name, force, self.db_writer)

        # Check if data is stale
        if self._should_update_source(source_name) or force:
            self.detail_logger.info(f"Data for {backend_name} is stale, updating...")
            return await self._fetch_backend_data(source_name, force, self.db_writer)

        self.detail_logger.debug(f"Data for {backend_name} is fresh, no update needed")
        return {"status": "current", "reason": "data_fresh"}

    async def _cleanup_disabled_backend_data(
        self, backend: Backend, show_progress: bool = True
    ) -> dict[str, Any]:
        """Remove data for a disabled backend.

        Args:
            backend: Backend instance
            show_progress: Show progress output to console

        Returns:
            Dictionary with operation result
        """
        backend_name = backend.get_name()

        # Only handle CachedBackend types
        if not isinstance(backend, CachedBackend):
            self.detail_logger.debug(
                f"{backend_name}: Skipped cleanup (not a cached backend)"
            )
            return {"status": "skipped", "reason": "not_cached_backend"}

        source_name = backend.source_name

        # Check if data exists to clean up
        if not get_cache_manager().has_source_data(source_name):
            self.detail_logger.debug(f"{backend_name}: No data to cleanup")
            return {"status": "skipped", "reason": "no_data_to_cleanup"}

        # Remove data from cache
        try:
            deleted_count = get_cache_manager().remove_source_data(source_name)
            get_cache_manager().log_update(
                source_name,
                "cleanup",
                "success",
                0,
                error_message=f"Cleaned up {deleted_count} records for disabled backend",
            )

            self.detail_logger.info(
                f"Cleaned up {deleted_count} records for disabled backend {backend_name}"
            )
            return {"status": "cleaned", "records_removed": deleted_count}

        except Exception as e:
            self.detail_logger.error(f"Failed to cleanup data for {backend_name}: {e}")
            get_cache_manager().log_update(
                source_name, "cleanup", "failed", 0, error_message=str(e)
            )
            return {"status": "error", "error": str(e)}

    async def _fetch_backend_data(
        self, source_name: str, force: bool = False, db_writer: Any = None
    ) -> dict[str, str | int]:
        """Fetch data for a specific source.

        Args:
            source_name: Name of the data source
            force: Force update even if not needed

        Returns:
            Dictionary with operation result
        """
        # Find the corresponding data source for this backend
        for source in data_updater.sources:
            if source.get_name() == source_name:
                try:
                    self.detail_logger.debug(
                        f"Fetching data for source {source_name} (force={force})"
                    )
                    result = await data_updater.update_source(
                        source, force=force, db_writer=db_writer
                    )
                    self.detail_logger.info(
                        f"Successfully fetched data for {source_name}: {result}"
                    )
                    return result
                except Exception as e:
                    self.detail_logger.error(
                        f"Failed to update source {source_name}: {e}"
                    )
                    self.detail_logger.exception("Detailed error:")
                    return {"status": "error", "error": str(e)}

        self.detail_logger.error(f"No data source found for {source_name}")
        return {
            "status": "error",
            "error": f"No data source configured for {source_name}",
        }

    def _should_update_source(self, source_name: str) -> bool:
        """Check if a source should be updated based on age.

        Args:
            source_name: Name of the source to check

        Returns:
            True if source should be updated
        """
        # Get configuration settings
        config = self.config_manager.load_config()
        cache_config = getattr(config, "cache", None)
        threshold_days = (
            getattr(cache_config, "update_threshold_days", 7) if cache_config else 7
        )

        last_update = get_cache_manager().get_source_last_updated(source_name)
        if last_update is None:
            return True  # Never updated

        # Check if older than threshold
        age_days = (datetime.now() - last_update).days
        return age_days >= threshold_days

    def get_sync_status(self) -> dict[str, Any]:
        """Get current synchronization status for all backends.

        Returns:
            Dictionary with status information for each backend
        """
        status: dict[str, Any] = {
            "sync_in_progress": self.sync_in_progress,
            "backends": {},
        }

        backend_registry = get_backend_registry()
        all_backend_names = backend_registry.get_backend_names()
        enabled_backend_names = self.config_manager.get_enabled_backends()
        available_sources = get_cache_manager().get_available_sources()

        for backend_name in all_backend_names:
            try:
                backend = backend_registry.get_backend(backend_name)
                is_enabled = backend_name in enabled_backend_names

                backend_status: dict[str, bool | str | int | datetime | None] = {
                    "enabled": is_enabled,
                    "type": (
                        "hybrid" if isinstance(backend, HybridBackend) else "cached"
                    ),
                    "has_data": False,
                    "last_updated": None,
                }

                if isinstance(backend, CachedBackend):
                    source_name = backend.source_name
                    backend_status["source_name"] = source_name
                    backend_status["has_data"] = source_name in available_sources
                    backend_status["last_updated"] = (
                        get_cache_manager().get_source_last_updated(source_name)
                    )

                    # Get entry count for the source
                    source_stats = get_cache_manager().get_source_statistics()
                    if source_name in source_stats:
                        backend_status["entry_count"] = source_stats[source_name].get(
                            "total", 0
                        )
                    else:
                        backend_status["entry_count"] = 0

                status["backends"][backend_name] = backend_status

            except Exception as e:
                status["backends"][backend_name] = {"error": str(e)}

        return status


# Global cache sync manager instance
cache_sync_manager = CacheSyncManager()
