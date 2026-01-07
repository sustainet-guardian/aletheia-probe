# SPDX-License-Identifier: MIT
"""Standalone utility functions for data source synchronization."""

from datetime import datetime
from typing import Any, cast

from ..cache import DataSourceManager
from ..cache_sync.db_writer import AsyncDBWriter
from ..data_models import JournalDataDict
from ..enums import UpdateStatus, UpdateType
from ..logging_config import get_detail_logger, get_status_logger
from .core import DataSource


async def update_source_data(
    source: DataSource,
    db_writer: AsyncDBWriter,
    force: bool = False,
) -> dict[str, Any]:
    """Update database from a data source.

    Standalone utility function for syncing data from any DataSource
    to the cache database via AsyncDBWriter.

    Args:
        source: DataSource instance to fetch data from
        db_writer: AsyncDBWriter for queuing database writes
        force: Force update even if source.should_update() returns False

    Returns:
        Dictionary with operation result:
        - status: "success", "skipped", or "failed"
        - records_updated: Number of records (on success)
        - processing_time: Time taken in seconds (on success)
        - error: Error message (on failure)
        - reason: Skip reason (when skipped)
    """
    source_name = source.get_name()
    status_logger = get_status_logger()
    detail_logger = get_detail_logger()
    detail_logger.info(f"Updating source: {source_name}")

    if not force and not source.should_update():
        # Allow source to provide a specific reason for skipping
        reason = getattr(source, "skip_reason", "no_update_needed")
        detail_logger.info(f"Source {source_name} does not need updating: {reason}")
        return {"status": "skipped", "reason": reason}

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

        # Queue the data for asynchronous writing
        # Cast to JournalDataDict list - data sources return dicts that conform to this structure
        await db_writer.queue_write(
            source_name,
            source.get_list_type(),
            cast(list[JournalDataDict], journals),
        )
        records_updated = len(journals)
        status_logger.info(
            f"    {source_name}: Queued {records_updated} records for writing"
        )
        # Note: log_update will be called by the db_writer when actually writing

        detail_logger.info(
            f"Successfully updated {source_name}: {records_updated} records"
        )
        return {
            "status": "success",
            "records_updated": records_updated,
            "processing_time": (datetime.now() - start_time).total_seconds(),
        }

    except (ValueError, OSError, KeyError) as e:
        detail_logger.error(f"Failed to update source {source_name}: {e}")
        status_logger.error(f"    {source_name}: Error - {e}")
        data_source_manager.log_update(
            source_name,
            UpdateType.FULL.value,
            UpdateStatus.FAILED.value,
            error_message=str(e),
        )
        return {"status": "failed", "error": str(e)}
