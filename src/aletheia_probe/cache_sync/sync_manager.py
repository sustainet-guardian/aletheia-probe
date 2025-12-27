# SPDX-License-Identifier: MIT
"""Cache synchronization manager for automatic backend data management."""

import asyncio
import sqlite3
from datetime import datetime
from typing import Any

from ..backends.base import Backend, CachedBackend, HybridBackend, get_backend_registry
from ..cache import DataSourceManager
from ..config import get_config_manager
from ..enums import UpdateStatus
from ..logging_config import get_detail_logger, get_status_logger
from ..updater import data_updater  # Global updater instance from updater package
from .db_writer import AsyncDBWriter


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
                    return {
                        "status": UpdateStatus.ERROR.value,
                        "error": "No matching backends found",
                    }
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
                            "status": UpdateStatus.SKIPPED.value,
                            "reason": "not_cached_backend",
                        }
                except (
                    KeyError,
                    AttributeError,
                    ValueError,
                    TypeError,
                    ImportError,
                    RuntimeError,
                ) as e:
                    # If we can't get the backend, mark as error and skip
                    self.detail_logger.exception(
                        f"Error getting backend {backend_name}: {e}"
                    )
                    sync_results[backend_name] = {
                        "status": UpdateStatus.ERROR.value,
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

            # Process all backends with controlled concurrency (5 at a time)
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
                        "status": UpdateStatus.ERROR.value,
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
                    self._log_backend_result(
                        backend_name, sync_results[backend_name], show_progress
                    )

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

    def _log_backend_result(
        self, backend_name: str, result_value: str | dict[str, Any], show_progress: bool
    ) -> None:
        """Log backend synchronization result to status logger.

        Args:
            backend_name: Name of the backend that was processed
            result_value: Result dictionary or string from backend processing
            show_progress: Whether to show progress output to console
        """
        if not show_progress:
            return

        if isinstance(result_value, dict):
            status = result_value.get("status", "unknown")
            if status == UpdateStatus.SUCCESS.value:
                count = result_value.get("records_updated", 0)
                self.status_logger.info(f"  {backend_name}: Updated {count} records")
            elif status == UpdateStatus.CURRENT.value:
                self.status_logger.info(f"  {backend_name}: Data is current")
            elif status == UpdateStatus.CLEANED.value:
                count = result_value.get("records_removed", 0)
                self.status_logger.info(
                    f"  {backend_name}: Cleaned {count} records (disabled)"
                )
            elif status == UpdateStatus.SKIPPED.value:
                reason = result_value.get("reason", "")
                self.status_logger.info(f"  {backend_name}: Skipped ({reason})")
            elif status == UpdateStatus.FAILED.value:
                self.status_logger.warning(f"  {backend_name}: Failed")
            elif status == UpdateStatus.ERROR.value:
                error = result_value.get("error", "unknown error")
                self.status_logger.error(f"  {backend_name}: Error - {error}")
            else:
                self.status_logger.info(f"  {backend_name}: {status}")
        elif isinstance(result_value, str):
            self.status_logger.info(f"  {backend_name}: {result_value}")

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
                except (
                    sqlite3.Error,
                    ValueError,
                    KeyError,
                    AttributeError,
                ) as e:
                    self.detail_logger.exception(
                        f"Error cleaning up {backend_name}: {e}"
                    )
                    return {"status": UpdateStatus.ERROR.value, "error": str(e)}
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
            except (sqlite3.Error, KeyError, AttributeError, OSError) as e:
                self.detail_logger.exception(
                    f"Unexpected error syncing backend {backend_name}: {e}"
                )
                if show_progress:
                    self.status_logger.error(
                        f"  {backend_name}: {type(e).__name__} - {e}"
                    )
                return {
                    "status": UpdateStatus.ERROR.value,
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
            return {
                "status": UpdateStatus.SKIPPED.value,
                "reason": "not_cached_backend",
            }

        source_name = backend.source_name

        # Check if data exists
        data_source_manager = DataSourceManager()
        has_data = data_source_manager.has_source_data(source_name)

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
        return {"status": UpdateStatus.CURRENT.value, "reason": "data_fresh"}

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
            return {
                "status": UpdateStatus.SKIPPED.value,
                "reason": "not_cached_backend",
            }

        source_name = backend.source_name
        data_source_manager = DataSourceManager()

        # Check if data exists to clean up
        if not data_source_manager.has_source_data(source_name):
            self.detail_logger.debug(f"{backend_name}: No data to cleanup")
            return {
                "status": UpdateStatus.SKIPPED.value,
                "reason": "no_data_to_cleanup",
            }

        # Remove data from cache
        try:
            deleted_count = data_source_manager.remove_source_data(source_name)
            data_source_manager.log_update(
                source_name,
                "cleanup",
                "success",
                0,
                error_message=f"Cleaned up {deleted_count} records for disabled backend",
            )

            self.detail_logger.info(
                f"Cleaned up {deleted_count} records for disabled backend {backend_name}"
            )
            return {
                "status": UpdateStatus.CLEANED.value,
                "records_removed": deleted_count,
            }

        except (sqlite3.Error, ValueError, KeyError) as e:
            self.detail_logger.error(f"Failed to cleanup data for {backend_name}: {e}")
            data_source_manager.log_update(
                source_name, "cleanup", "failed", 0, error_message=str(e)
            )
            return {"status": UpdateStatus.ERROR.value, "error": str(e)}

    async def _fetch_backend_data(
        self,
        source_name: str,
        force: bool = False,
        db_writer: AsyncDBWriter | None = None,
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
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    AttributeError,
                    sqlite3.Error,
                ) as e:
                    self.detail_logger.error(
                        f"Failed to update source {source_name}: {e}"
                    )
                    self.detail_logger.exception("Detailed error:")
                    return {"status": UpdateStatus.ERROR.value, "error": str(e)}

        self.detail_logger.error(f"No data source found for {source_name}")
        return {
            "status": UpdateStatus.ERROR.value,
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

        data_source_manager = DataSourceManager()
        last_update = data_source_manager.get_source_last_updated(source_name)
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
        data_source_manager = DataSourceManager()
        available_sources = data_source_manager.get_available_sources()

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
                        data_source_manager.get_source_last_updated(source_name)
                    )

                    # Get entry count for the source
                    source_stats = data_source_manager.get_source_statistics()
                    if source_name in source_stats:
                        backend_status["entry_count"] = source_stats[source_name].get(
                            "total", 0
                        )
                    else:
                        backend_status["entry_count"] = 0

                status["backends"][backend_name] = backend_status

            except (
                AttributeError,
                KeyError,
                ValueError,
                RuntimeError,
                sqlite3.Error,
            ) as e:
                status["backends"][backend_name] = {"error": str(e)}

        return status
