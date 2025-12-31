# SPDX-License-Identifier: MIT
"""Asynchronous database writer for cache synchronization."""

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ..cache import DataSourceManager, RetractionCache
from ..data_models import JournalDataDict
from ..enums import NameType, UpdateStatus, UpdateType
from ..logging_config import get_detail_logger, get_status_logger


class AsyncDBWriter:
    """Handles database writes asynchronously to prevent blocking."""

    def __init__(self) -> None:
        """Initialize the database writer with an empty queue and loggers."""
        self.write_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.writer_task: asyncio.Task[None] | None = None
        self.detail_logger = get_detail_logger()
        self.status_logger = get_status_logger()

    async def start_writer(self) -> None:
        """Start the database writer task.

        Creates an asynchronous task that processes the write queue. Does nothing
        if the writer task is already running.
        """
        if self.writer_task is None:
            self.status_logger.info("    DBWriter: Starting database writer task...")
            self.detail_logger.debug("Creating async task for database writer loop")
            self.writer_task = asyncio.create_task(self._db_writer_loop())

    async def stop_writer(self) -> None:
        """Stop the database writer task.

        Sends a shutdown signal to the writer loop and waits for it to complete.
        Does nothing if the writer task is not running.
        """
        if self.writer_task:
            self.status_logger.info("    DBWriter: Stopping database writer task...")
            self.detail_logger.debug("Sending shutdown signal (None) to write queue")
            await self.write_queue.put(None)  # Signal to stop
            self.detail_logger.debug("Waiting for writer task to complete")
            await self.writer_task
            self.writer_task = None
            self.status_logger.info("    DBWriter: Database writer task stopped")

    async def queue_write(
        self, source_name: str, list_type: str, journals: list[JournalDataDict]
    ) -> None:
        """Queue data for database writing.

        Args:
            source_name: Name of the data source
            list_type: Type of list (e.g., "predatory", "legitimate")
            journals: List of journal data dictionaries conforming to JournalDataDict structure
        """
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
        """Main database writer loop - processes write queue sequentially.

        Continuously processes items from the write queue until a shutdown signal
        (None) is received. Handles database errors gracefully and logs them.
        """
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
        """Configure SQLite performance optimizations for batch operations.

        Args:
            conn: SQLite database connection to configure
        """
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
        data_source_manager: DataSourceManager,
        source_name: str,
        list_type: str,
    ) -> int:
        """Ensure data source is registered and return its ID.

        Args:
            data_source_manager: Manager for data source registration
            source_name: Name of the data source to register
            list_type: Type of list (e.g., "predatory", "legitimate")

        Returns:
            Database ID of the registered data source
        """
        self.detail_logger.debug(f"Ensuring data source is registered: {source_name}")
        source_id = data_source_manager.register_data_source(
            source_name, source_name, list_type
        )
        self.detail_logger.debug(f"Data source ID for {source_name}: {source_id}")
        return source_id

    def _prepare_journal_batch_data(
        self, journals: list[JournalDataDict]
    ) -> tuple[
        list[str],
        set[str],
        list[tuple[str, str, str | None, str | None, str | None]],
        int,
    ]:
        """Prepare journal data for batch upsert.

        Args:
            journals: List of journal data dictionaries to process

        Returns:
            Tuple of (normalized_names, unique_names, upsert_records, total_records)
        """
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

            journal_upserts.append(
                (
                    normalized_name,
                    journal["journal_name"],
                    journal.get("issn"),
                    journal.get("eissn"),
                    journal.get("publisher"),
                )
            )

        return (
            normalized_names,
            unique_normalized_names,
            journal_upserts,
            total_input_records,
        )

    def _upsert_journals_batch(
        self,
        cursor: sqlite3.Cursor,
        journal_upserts: list[tuple[str, str, str | None, str | None, str | None]],
    ) -> None:
        """Execute batch upsert of journals to database.

        Args:
            cursor: Database cursor for executing queries
            journal_upserts: List of journal tuples to upsert
        """
        if journal_upserts:
            cursor.executemany(
                """INSERT INTO journals (normalized_name, display_name, issn, eissn, publisher)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(normalized_name) DO UPDATE SET
                       display_name = excluded.display_name,
                       issn = excluded.issn,
                       eissn = excluded.eissn,
                       publisher = excluded.publisher""",
                journal_upserts,
            )

    def _prepare_and_upsert_journals(
        self,
        cursor: sqlite3.Cursor,
        journals: list[JournalDataDict],
    ) -> tuple[list[str], int, int]:
        """Prepare journal data and upsert to database.

        Args:
            cursor: Database cursor for executing queries
            journals: List of journal data dictionaries to upsert

        Returns:
            Tuple containing (normalized_names, unique_journals, total_input_records)
        """
        self.detail_logger.debug(
            f"Preparing journal upserts for {len(journals)} records"
        )

        normalized_names, unique_names, journal_upserts, total_input = (
            self._prepare_journal_batch_data(journals)
        )

        self.detail_logger.debug(
            f"Executing journal upserts: {len(journal_upserts)} records, "
            f"{len(unique_names)} unique journals"
        )
        self._upsert_journals_batch(cursor, journal_upserts)

        unique_journals = len(unique_names)
        self.detail_logger.debug(
            f"Journal upserts completed: total_input={total_input}, unique={unique_journals}"
        )
        return normalized_names, unique_journals, total_input

    def _get_journal_ids(
        self, cursor: sqlite3.Cursor, normalized_names: list[str]
    ) -> dict[str, int]:
        """Retrieve journal IDs for the given normalized names.

        Args:
            cursor: Database cursor for executing queries
            normalized_names: List of normalized journal names to look up

        Returns:
            Dictionary mapping normalized names to their database IDs
        """
        if not normalized_names:
            self.detail_logger.debug("No normalized names to retrieve journal IDs for")
            return {}

        self.detail_logger.debug(
            f"Retrieving journal IDs for {len(normalized_names)} normalized names"
        )
        # Dynamic query construction with parameterized placeholders
        # SAFETY: placeholders contains only "?" characters (SQLite parameter markers)
        # The actual normalized_names values are passed separately to cursor.execute()
        # and are safely bound by SQLite, preventing SQL injection.
        # This pattern is verified by test_sql_injection_protection_in_get_journal_ids
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

    def _collect_urls_from_value(self, value: Any, url_set: set[str]) -> None:
        """Collect valid URLs from a value and add them to a set.

        Handles both single URL strings and lists of URLs. Validates that
        URLs are non-empty strings and strips whitespace before adding.

        Args:
            value: Single URL string or list of URL strings
            url_set: Set to add validated URLs to
        """
        if isinstance(value, list):
            for url in value:
                if url and isinstance(url, str) and url.strip():
                    url_set.add(url.strip())
        elif isinstance(value, str) and value.strip():
            url_set.add(value.strip())

    def _extract_urls_from_journal(self, journal: JournalDataDict) -> set[str]:
        """Extract and deduplicate URLs from journal data.

        Args:
            journal: Journal data dictionary with potential URLs

        Returns:
            Set of unique, non-empty URL strings
        """
        urls_to_insert: set[str] = set()

        if journal.get("urls"):
            self._collect_urls_from_value(journal["urls"], urls_to_insert)

        metadata = journal.get("metadata")
        if metadata:
            for field in ("urls", "website_url", "source_url"):
                if field in metadata and metadata[field]:
                    self._collect_urls_from_value(metadata[field], urls_to_insert)

        return urls_to_insert

    def _prepare_related_data(
        self,
        journals: list[JournalDataDict],
        existing_journals: dict[str, int],
        source_id: int,
        source_name: str,
        list_type: str,
    ) -> tuple[
        list[tuple[int, str, str, str]],
        list[tuple[int, int, str, float]],
        list[tuple[int, str]],
    ]:
        """Prepare batch data for related tables.

        Args:
            journals: List of journal data dictionaries
            existing_journals: Mapping of normalized names to journal IDs
            source_id: Database ID of the data source
            source_name: Name of the data source
            list_type: Type of list (e.g., "predatory", "legitimate")

        Returns:
            Tuple of (name_inserts, assessment_inserts, url_inserts)
        """
        self.detail_logger.debug(
            f"Preparing related data for {len(journals)} journals, "
            f"{len(existing_journals)} existing journal IDs"
        )
        name_inserts = []
        assessment_inserts = []
        url_inserts = []

        for journal in journals:
            normalized_name = journal.get("normalized_name")
            if not normalized_name or normalized_name not in existing_journals:
                continue

            journal_id = existing_journals[normalized_name]

            name_inserts.append(
                (
                    journal_id,
                    journal["journal_name"],
                    NameType.CANONICAL.value,
                    source_name,
                )
            )
            assessment_inserts.append((journal_id, source_id, list_type, 1.0))
            url_inserts.extend(
                [(journal_id, url) for url in self._extract_urls_from_journal(journal)]
            )

        self.detail_logger.debug(
            f"Related data prepared: {len(name_inserts)} names, {len(assessment_inserts)} assessments, "
            f"{len(url_inserts)} URLs"
        )
        return name_inserts, assessment_inserts, url_inserts

    def _insert_journal_names(
        self, cursor: sqlite3.Cursor, name_inserts: list[tuple[int, str, str, str]]
    ) -> None:
        """Insert journal names into database.

        Args:
            cursor: Database cursor for executing queries
            name_inserts: List of journal name records to insert
        """
        if name_inserts:
            self.detail_logger.debug(f"Inserting {len(name_inserts)} journal names")
            cursor.executemany(
                """INSERT OR IGNORE INTO journal_names
                   (journal_id, name, name_type, source_name)
                   VALUES (?, ?, ?, ?)""",
                name_inserts,
            )

    def _insert_assessments(
        self,
        cursor: sqlite3.Cursor,
        assessment_inserts: list[tuple[int, int, str, float]],
    ) -> None:
        """Insert source assessments into database.

        Args:
            cursor: Database cursor for executing queries
            assessment_inserts: List of source assessment records to insert
        """
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

    def _insert_article_retractions(
        self,
        source_name: str,
        journals: list[JournalDataDict],
    ) -> None:
        """Insert article retractions for RetractionWatch.

        Args:
            source_name: Name of the data source
            journals: List of journal data dictionaries
        """
        if source_name != "retraction_watch":
            return

        # Extract article retractions from metadata (stored in first journal)
        article_retractions = []
        if journals:
            metadata: dict[str, Any] = journals[0].get("metadata", {})
            article_retractions = metadata.get("_article_retractions", [])

        if not article_retractions:
            return

        retraction_cache = RetractionCache()

        # Batch insert article retractions
        with sqlite3.connect(retraction_cache.db_path) as conn:
            cursor = conn.cursor()
            records = [
                (
                    article["doi"],
                    article["is_retracted"],
                    article["retraction_type"],
                    article["retraction_date"],
                    article["retraction_doi"],
                    article["retraction_reason"],
                    article["source"],
                    article["expires_at"],
                )
                for article in article_retractions
            ]

            cursor.executemany(
                """
                INSERT OR REPLACE INTO article_retractions
                (doi, is_retracted, retraction_type, retraction_date, retraction_doi,
                 retraction_reason, source, checked_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                records,
            )
            conn.commit()

        self.detail_logger.debug(
            f"Inserted {len(article_retractions)} article retraction records"
        )
        self.status_logger.info(
            f"    DBWriter: Inserted {len(article_retractions):,} article retraction records"
        )

    def _insert_retraction_statistics(
        self,
        source_name: str,
        journals: list[JournalDataDict],
        existing_journals: dict[str, int],
    ) -> None:
        """Insert retraction statistics for RetractionWatch journals.

        Args:
            source_name: Name of the data source
            journals: List of journal data dictionaries
            existing_journals: Mapping of normalized names to journal IDs
        """
        if source_name != "retraction_watch":
            return

        retraction_cache = RetractionCache()
        stats_count = 0

        for journal in journals:
            normalized_name = journal.get("normalized_name")
            if not normalized_name or normalized_name not in existing_journals:
                continue

            journal_id = existing_journals[normalized_name]
            metadata: dict[str, Any] = journal.get("metadata", {})

            if metadata:
                retraction_cache.upsert_retraction_statistics(
                    journal_id=journal_id,
                    total_retractions=metadata.get("total_retractions", 0),
                    recent_retractions=metadata.get("recent_retractions", 0),
                    very_recent_retractions=metadata.get("very_recent_retractions", 0),
                    retraction_types=metadata.get("retraction_types"),
                    top_reasons=metadata.get("top_reasons"),
                    publishers=metadata.get("publishers"),
                    first_retraction_date=metadata.get("first_retraction_date"),
                    last_retraction_date=metadata.get("last_retraction_date"),
                )
                stats_count += 1

        if stats_count > 0:
            self.detail_logger.debug(
                f"Inserted {stats_count} retraction statistics records"
            )

    def _insert_urls(
        self, cursor: sqlite3.Cursor, url_inserts: list[tuple[int, str]]
    ) -> None:
        """Insert journal URLs into database.

        Args:
            cursor: Database cursor for executing queries
            url_inserts: List of journal URL records to insert
        """
        if url_inserts:
            self.detail_logger.debug(f"Inserting {len(url_inserts)} journal URLs")
            cursor.executemany(
                """INSERT OR REPLACE INTO journal_urls
                   (journal_id, url, last_seen_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                url_inserts,
            )

    def _execute_batch_inserts(
        self,
        cursor: sqlite3.Cursor,
        name_inserts: list[tuple[int, str, str, str]],
        assessment_inserts: list[tuple[int, int, str, float]],
        url_inserts: list[tuple[int, str]],
    ) -> None:
        """Execute all batch insert operations.

        Args:
            cursor: Database cursor for executing queries
            name_inserts: List of journal name records to insert
            assessment_inserts: List of source assessment records to insert
            url_inserts: List of journal URL records to insert
        """
        self.detail_logger.debug("Executing batch inserts for related tables")
        self._insert_journal_names(cursor, name_inserts)
        self._insert_assessments(cursor, assessment_inserts)
        self._insert_urls(cursor, url_inserts)
        self.detail_logger.debug("Batch inserts completed")

    def _execute_transaction(
        self,
        cursor: sqlite3.Cursor,
        conn: sqlite3.Connection,
        journals: list[JournalDataDict],
        source_id: int,
        source_name: str,
        list_type: str,
    ) -> tuple[int, int]:
        """Execute database transaction for journal batch write.

        Args:
            cursor: Database cursor for executing queries
            conn: Database connection for transaction control
            journals: List of journal data dictionaries to write
            source_id: Database ID of the data source
            source_name: Name of the data source
            list_type: Type of list (e.g., "predatory", "legitimate")

        Returns:
            Tuple of (unique_journals, total_input_records)
        """
        normalized_names, unique_journals, total_input_records = (
            self._prepare_and_upsert_journals(cursor, journals)
        )

        existing_journals = self._get_journal_ids(cursor, normalized_names)

        name_inserts, assessment_inserts, url_inserts = self._prepare_related_data(
            journals, existing_journals, source_id, source_name, list_type
        )

        self._execute_batch_inserts(
            cursor, name_inserts, assessment_inserts, url_inserts
        )

        # Insert article retractions for retraction_watch source (before statistics)
        self._insert_article_retractions(source_name, journals)

        # Insert retraction statistics for retraction_watch source
        self._insert_retraction_statistics(source_name, journals, existing_journals)

        return unique_journals, total_input_records

    @contextmanager
    def _database_transaction(
        self, conn: sqlite3.Connection
    ) -> Iterator[sqlite3.Connection]:
        """Context manager for database transaction with automatic commit/rollback.

        Args:
            conn: SQLite database connection

        Yields:
            The database connection with an active transaction

        Raises:
            sqlite3.Error: Database operation errors
            KeyError: Missing required keys in data
            ValueError: Invalid data values
            TypeError: Incorrect data types
        """
        self.detail_logger.debug("Beginning database transaction")
        conn.execute("BEGIN TRANSACTION")

        try:
            yield conn
            self.detail_logger.debug("Committing database transaction")
            conn.execute("COMMIT")
            self.detail_logger.debug("Transaction committed successfully")
        except (sqlite3.Error, KeyError, ValueError, TypeError) as e:
            self.detail_logger.debug("Rolling back database transaction due to error")
            conn.execute("ROLLBACK")
            self.status_logger.error(f"Transaction error: {e}")
            self.detail_logger.exception("Detailed transaction error")
            raise

    def _batch_write_journals(
        self, source_name: str, list_type: str, journals: list[JournalDataDict]
    ) -> dict[str, int]:
        """Optimized batch writing of journals to database using SQLite performance tuning.

        Args:
            source_name: Name of the data source
            list_type: Type of list (e.g., "predatory", "legitimate")
            journals: List of journal data dictionaries to write

        Returns:
            Dictionary with keys: total_records, unique_journals, duplicates

        Raises:
            sqlite3.Error: Database operation errors
            KeyError: Missing required keys in journal data
            ValueError: Invalid data values
            TypeError: Incorrect data types
        """
        self.detail_logger.debug(
            f"Starting batch write: source={source_name}, list_type={list_type}, "
            f"journal_count={len(journals)}"
        )
        data_source_manager = DataSourceManager()

        with sqlite3.connect(data_source_manager.db_path) as conn:
            self._setup_db_connection(conn)
            cursor = conn.cursor()

            source_id = self._ensure_source_registered(
                data_source_manager, source_name, list_type
            )

            with self._database_transaction(conn):
                unique_journals, total_input_records = self._execute_transaction(
                    cursor, conn, journals, source_id, source_name, list_type
                )

                return {
                    "total_records": total_input_records,
                    "unique_journals": unique_journals,
                    "duplicates": total_input_records - unique_journals,
                }
