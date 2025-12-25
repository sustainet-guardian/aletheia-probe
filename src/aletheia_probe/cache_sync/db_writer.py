# SPDX-License-Identifier: MIT
"""Asynchronous database writer for cache synchronization."""

import asyncio
import json
import sqlite3
from typing import Any

from ..cache import DataSourceManager
from ..logging_config import get_status_logger


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

                data_source_manager = DataSourceManager()
                data_source_manager.log_update(
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

            except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
                self.status_logger.error(f"Database write error: {e}")

    def _batch_write_journals(
        self, source_name: str, list_type: str, journals: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Optimized batch writing of journals to database using SQLite performance tuning."""
        data_source_manager = DataSourceManager()

        # Get database connection with performance optimizations
        with sqlite3.connect(data_source_manager.db_path) as conn:
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
                data_source_manager.register_data_source(
                    source_name, source_name, list_type
                )
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
                url_inserts = []

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

                    # URLs - Extract from multiple sources and deduplicate
                    urls_to_insert = set()  # Use set for automatic deduplication

                    # Check for top-level urls field
                    if journal.get("urls"):
                        for url in journal["urls"]:
                            if url and isinstance(url, str) and url.strip():
                                urls_to_insert.add(url.strip())

                    # Extract URLs from metadata
                    if metadata:
                        # Handle Algerian Ministry format: metadata["urls"] as list
                        if "urls" in metadata and isinstance(metadata["urls"], list):
                            for url in metadata["urls"]:
                                if url and isinstance(url, str) and url.strip():
                                    urls_to_insert.add(url.strip())

                        # Handle Kscien format: metadata["website_url"] as string
                        if "website_url" in metadata and metadata["website_url"]:
                            url = metadata["website_url"]
                            if isinstance(url, str) and url.strip():
                                urls_to_insert.add(url.strip())

                        # Handle other potential URL fields in metadata
                        if "source_url" in metadata and metadata["source_url"]:
                            url = metadata["source_url"]
                            if isinstance(url, str) and url.strip():
                                urls_to_insert.add(url.strip())

                    # Add deduplicated URLs to batch inserts
                    for url in urls_to_insert:
                        url_inserts.append((journal_id, url))

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

                # Batch insert/update journal URLs
                if url_inserts:
                    cursor.executemany(
                        """INSERT OR REPLACE INTO journal_urls
                           (journal_id, url, last_seen_at)
                           VALUES (?, ?, CURRENT_TIMESTAMP)""",
                        url_inserts,
                    )

                # Commit transaction
                conn.execute("COMMIT")

                return {
                    "total_records": total_input_records,
                    "unique_journals": unique_journals,
                    "duplicates": total_input_records - unique_journals,
                }

            except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
                conn.execute("ROLLBACK")
                self.status_logger.error(f"Batch write error: {e}")
                raise
