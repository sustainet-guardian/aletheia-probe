# SPDX-License-Identifier: MIT
"""Asynchronous database writer for cache synchronization."""

import asyncio
import json
import sqlite3
from typing import Any

from ..cache import DataSourceManager
from ..enums import NameType, UpdateStatus, UpdateType
from ..logging_config import get_detail_logger, get_status_logger


class AsyncDBWriter:
    """Handles database writes asynchronously to prevent blocking."""

    def __init__(self) -> None:
        self.write_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.writer_task: asyncio.Task[None] | None = None
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    async def start_writer(self) -> None:
        """Start the database writer task."""
        if self.writer_task is None:
            self.status_logger.info("    DBWriter: Starting database writer task...")
            self.detail_logger.debug("Creating async task for database writer loop")
            self.writer_task = asyncio.create_task(self._db_writer_loop())

    async def stop_writer(self) -> None:
        """Stop the database writer task."""
        if self.writer_task:
            self.status_logger.info("    DBWriter: Stopping database writer task...")
            self.detail_logger.debug("Sending shutdown signal (None) to write queue")
            await self.write_queue.put(None)  # Signal to stop
            self.detail_logger.debug("Waiting for writer task to complete")
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
        self.detail_logger.debug(
            f"Queueing write operation: source={source_name}, list_type={list_type}, "
            f"record_count={len(journals)}, current_queue_size={self.write_queue.qsize()}"
        )
        await self.write_queue.put(
            {"source_name": source_name, "list_type": list_type, "journals": journals}
        )
        self.status_logger.info(
            f"    DBWriter: Queued {len(journals)} records from {source_name}"
        )

    async def _db_writer_loop(self) -> None:
        """Main database writer loop - processes write queue sequentially."""
        self.detail_logger.debug("Database writer loop started")
        while True:
            try:
                self.detail_logger.debug("Waiting for next item from write queue")
                write_data = await self.write_queue.get()

                # None signals shutdown
                if write_data is None:
                    self.detail_logger.debug(
                        "Received shutdown signal, exiting writer loop"
                    )
                    break

                source_name = write_data["source_name"]
                list_type = write_data["list_type"]
                journals = write_data["journals"]

                self.status_logger.info(
                    f"    DBWriter: Processing {source_name} - Writing {len(journals)} records to database..."
                )
                self.detail_logger.debug(
                    f"Dequeued write operation: source={source_name}, list_type={list_type}, "
                    f"record_count={len(journals)}"
                )

                # Perform optimized batch database writes
                write_result = self._batch_write_journals(
                    source_name, list_type, journals
                )

                total_records = write_result["total_records"]
                unique_journals = write_result["unique_journals"]
                duplicates = write_result["duplicates"]

                self.detail_logger.debug(
                    f"Batch write completed: total_records={total_records}, "
                    f"unique_journals={unique_journals}, duplicates={duplicates}"
                )

                data_source_manager = DataSourceManager()
                data_source_manager.log_update(
                    source_name,
                    UpdateType.FULL.value,
                    UpdateStatus.SUCCESS.value,
                    records_updated=total_records,
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
                self.detail_logger.exception(
                    f"Detailed database write error for {source_name}"
                )

    def _setup_db_connection(self, conn: sqlite3.Connection) -> None:
        """Configure SQLite performance optimizations for batch operations."""
        self.detail_logger.debug(
            "Configuring SQLite PRAGMA settings for batch operations"
        )
        conn.execute("PRAGMA journal_mode = WAL")
        self.detail_logger.debug("Set PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        self.detail_logger.debug("Set PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = 10000")
        self.detail_logger.debug("Set PRAGMA cache_size = 10000")
        conn.execute("PRAGMA temp_store = MEMORY")
        self.detail_logger.debug("Set PRAGMA temp_store = MEMORY")

    def _ensure_source_registered(
        self,
        cursor: sqlite3.Cursor,
        data_source_manager: DataSourceManager,
        source_name: str,
        list_type: str,
    ) -> int:
        """Ensure data source is registered and return its ID."""
        self.detail_logger.debug(
            f"Checking if data source is registered: {source_name}"
        )
        cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
        source_row = cursor.fetchone()
        if not source_row:
            self.detail_logger.debug(
                f"Data source not found, registering: {source_name} (list_type: {list_type})"
            )
            data_source_manager.register_data_source(
                source_name, source_name, list_type
            )
            cursor.execute("SELECT id FROM data_sources WHERE name = ?", (source_name,))
            source_row = cursor.fetchone()
        source_id = int(source_row[0])
        self.detail_logger.debug(f"Data source ID for {source_name}: {source_id}")
        return source_id

    def _prepare_and_upsert_journals(
        self,
        cursor: sqlite3.Cursor,
        journals: list[dict[str, Any]],
    ) -> tuple[list[str], int, int]:
        """Prepare journal data and upsert to database."""
        self.detail_logger.debug(
            f"Preparing journal upserts for {len(journals)} records"
        )
        normalized_names = []
        unique_normalized_names = set()
        journal_upserts = []
        total_input_records = 0

        for journal in journals:
            normalized_name = journal.get("normalized_name")
            if not normalized_name:
                continue

            total_input_records += 1
            unique_normalized_names.add(normalized_name)
            normalized_names.append(normalized_name)

            journal_name = journal["journal_name"]
            issn = journal.get("issn")
            eissn = journal.get("eissn")
            publisher = journal.get("publisher")

            journal_upserts.append(
                (normalized_name, journal_name, issn, eissn, publisher)
            )

        if journal_upserts:
            self.detail_logger.debug(
                f"Executing journal upserts: {len(journal_upserts)} records, "
                f"{len(unique_normalized_names)} unique journals"
            )
            cursor.executemany(
                """INSERT OR REPLACE INTO journals (normalized_name, display_name, issn, eissn, publisher)
                   VALUES (?, ?, ?, ?, ?)""",
                journal_upserts,
            )

        unique_journals = len(unique_normalized_names)
        self.detail_logger.debug(
            f"Journal upserts completed: total_input={total_input_records}, unique={unique_journals}"
        )
        return normalized_names, unique_journals, total_input_records

    def _get_journal_ids(
        self, cursor: sqlite3.Cursor, normalized_names: list[str]
    ) -> dict[str, int]:
        """Retrieve journal IDs for the given normalized names."""
        if not normalized_names:
            self.detail_logger.debug("No normalized names to retrieve journal IDs for")
            return {}

        self.detail_logger.debug(
            f"Retrieving journal IDs for {len(normalized_names)} normalized names"
        )
        placeholders = ",".join("?" * len(normalized_names))
        cursor.execute(
            f"SELECT id, normalized_name FROM journals WHERE normalized_name IN ({placeholders})",  # nosec B608
            normalized_names,
        )
        journal_ids = {row[1]: row[0] for row in cursor.fetchall()}
        self.detail_logger.debug(
            f"Retrieved {len(journal_ids)} journal IDs from database"
        )
        return journal_ids

    def _extract_urls_from_journal(self, journal: dict[str, Any]) -> set[str]:
        """Extract and deduplicate URLs from journal data."""
        urls_to_insert = set()

        if journal.get("urls"):
            for url in journal["urls"]:
                if url and isinstance(url, str) and url.strip():
                    urls_to_insert.add(url.strip())

        metadata = journal.get("metadata")
        if metadata:
            if "urls" in metadata and isinstance(metadata["urls"], list):
                for url in metadata["urls"]:
                    if url and isinstance(url, str) and url.strip():
                        urls_to_insert.add(url.strip())

            if "website_url" in metadata and metadata["website_url"]:
                url = metadata["website_url"]
                if isinstance(url, str) and url.strip():
                    urls_to_insert.add(url.strip())

            if "source_url" in metadata and metadata["source_url"]:
                url = metadata["source_url"]
                if isinstance(url, str) and url.strip():
                    urls_to_insert.add(url.strip())

        return urls_to_insert

    def _prepare_metadata_inserts(
        self, journal_id: int, source_id: int, metadata: dict[str, Any]
    ) -> list[tuple[int, int, str, str, str]]:
        """Prepare metadata insert records for batch operation."""
        metadata_inserts = []

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
                metadata_inserts.append((journal_id, source_id, key, value, data_type))

        return metadata_inserts

    def _prepare_related_data(
        self,
        journals: list[dict[str, Any]],
        existing_journals: dict[str, int],
        source_id: int,
        source_name: str,
        list_type: str,
    ) -> tuple[
        list[tuple[int, str, str, str]],
        list[tuple[int, int, str, float]],
        list[tuple[int, int, str, str, str]],
        list[tuple[int, str]],
    ]:
        """Prepare batch data for related tables."""
        self.detail_logger.debug(
            f"Preparing related data for {len(journals)} journals, "
            f"{len(existing_journals)} existing journal IDs"
        )
        name_inserts = []
        assessment_inserts = []
        metadata_inserts = []
        url_inserts = []

        for journal in journals:
            normalized_name = journal.get("normalized_name")
            if not normalized_name or normalized_name not in existing_journals:
                continue

            journal_id = existing_journals[normalized_name]
            journal_name = journal["journal_name"]
            metadata = journal.get("metadata")

            name_inserts.append(
                (journal_id, journal_name, NameType.CANONICAL.value, source_name)
            )

            assessment_inserts.append((journal_id, source_id, list_type, 1.0))

            urls_to_insert = self._extract_urls_from_journal(journal)
            for url in urls_to_insert:
                url_inserts.append((journal_id, url))

            if metadata:
                metadata_inserts.extend(
                    self._prepare_metadata_inserts(journal_id, source_id, metadata)
                )

        self.detail_logger.debug(
            f"Related data prepared: {len(name_inserts)} names, {len(assessment_inserts)} assessments, "
            f"{len(metadata_inserts)} metadata entries, {len(url_inserts)} URLs"
        )
        return name_inserts, assessment_inserts, metadata_inserts, url_inserts

    def _execute_batch_inserts(
        self,
        cursor: sqlite3.Cursor,
        name_inserts: list[tuple[int, str, str, str]],
        assessment_inserts: list[tuple[int, int, str, float]],
        metadata_inserts: list[tuple[int, int, str, str, str]],
        url_inserts: list[tuple[int, str]],
    ) -> None:
        """Execute all batch insert operations."""
        self.detail_logger.debug("Executing batch inserts for related tables")
        if name_inserts:
            self.detail_logger.debug(f"Inserting {len(name_inserts)} journal names")
            cursor.executemany(
                """INSERT OR IGNORE INTO journal_names
                   (journal_id, name, name_type, source_name)
                   VALUES (?, ?, ?, ?)""",
                name_inserts,
            )

        if assessment_inserts:
            self.detail_logger.debug(
                f"Inserting {len(assessment_inserts)} source assessments"
            )
            cursor.executemany(
                """INSERT OR REPLACE INTO source_assessments
                   (journal_id, source_id, assessment, confidence, last_confirmed_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                assessment_inserts,
            )

        if metadata_inserts:
            self.detail_logger.debug(
                f"Inserting {len(metadata_inserts)} metadata entries"
            )
            cursor.executemany(
                """INSERT OR REPLACE INTO source_metadata
                   (journal_id, source_id, metadata_key, metadata_value, data_type)
                   VALUES (?, ?, ?, ?, ?)""",
                metadata_inserts,
            )

        if url_inserts:
            self.detail_logger.debug(f"Inserting {len(url_inserts)} journal URLs")
            cursor.executemany(
                """INSERT OR REPLACE INTO journal_urls
                   (journal_id, url, last_seen_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                url_inserts,
            )
        self.detail_logger.debug("Batch inserts completed")

    def _batch_write_journals(
        self, source_name: str, list_type: str, journals: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Optimized batch writing of journals to database using SQLite performance tuning."""
        self.detail_logger.debug(
            f"Starting batch write: source={source_name}, list_type={list_type}, "
            f"journal_count={len(journals)}"
        )
        data_source_manager = DataSourceManager()

        with sqlite3.connect(data_source_manager.db_path) as conn:
            self._setup_db_connection(conn)
            cursor = conn.cursor()

            source_id = self._ensure_source_registered(
                cursor, data_source_manager, source_name, list_type
            )

            self.detail_logger.debug("Beginning database transaction")
            conn.execute("BEGIN TRANSACTION")

            try:
                normalized_names, unique_journals, total_input_records = (
                    self._prepare_and_upsert_journals(cursor, journals)
                )

                existing_journals = self._get_journal_ids(cursor, normalized_names)

                name_inserts, assessment_inserts, metadata_inserts, url_inserts = (
                    self._prepare_related_data(
                        journals, existing_journals, source_id, source_name, list_type
                    )
                )

                self._execute_batch_inserts(
                    cursor,
                    name_inserts,
                    assessment_inserts,
                    metadata_inserts,
                    url_inserts,
                )

                self.detail_logger.debug("Committing database transaction")
                conn.execute("COMMIT")
                self.detail_logger.debug("Transaction committed successfully")

                return {
                    "total_records": total_input_records,
                    "unique_journals": unique_journals,
                    "duplicates": total_input_records - unique_journals,
                }

            except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
                self.detail_logger.debug(
                    "Rolling back database transaction due to error"
                )
                conn.execute("ROLLBACK")
                self.status_logger.error(f"Batch write error: {e}")
                self.detail_logger.exception("Detailed batch write error")
                raise
