# SPDX-License-Identifier: MIT
"""Integration tests for AsyncDBWriter with real database.

INTEGRATION TEST FILE: This file contains integration tests that verify
AsyncDBWriter functionality with a real SQLite database, ensuring data
persistence, foreign key constraints, and referential integrity are properly
enforced. These tests use an in-memory database initialized with the actual
schema to catch logic errors that mocked tests might miss.
"""

import asyncio
import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aletheia_probe.cache import DataSourceManager, JournalCache, RetractionCache
from aletheia_probe.cache.schema import init_database
from aletheia_probe.cache_sync.db_writer import AsyncDBWriter
from aletheia_probe.enums import AssessmentType


class TestAsyncDBWriterIntegration:
    """Integration tests for AsyncDBWriter with real database."""

    @pytest.fixture
    def temp_db(self) -> Generator[Path, None, None]:
        """Create a temporary database file with initialized schema."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)
        init_database(db_path)
        yield db_path
        db_path.unlink()

    @pytest.fixture
    def db_writer(self, mock_data_source_manager) -> AsyncDBWriter:
        """Create AsyncDBWriter instance for testing."""
        return AsyncDBWriter()

    @pytest.fixture
    def mock_data_source_manager(self, temp_db: Path):
        """Mock DataSourceManager to use temporary test database."""
        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            # Create real instance with explicit db_path to avoid I/O operations
            mock_dsm = DataSourceManager(db_path=temp_db)
            mock_dsm_class.return_value = mock_dsm
            yield mock_dsm

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_single_sync_operation_data_persistence(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test data persistence with real database for single sync operation."""
        test_journals = [
            {
                "journal_name": "Test Journal Alpha",
                "normalized_name": "test_journal_alpha",
                "issn": "1234-5678",
                "eissn": "1234-5679",
                "publisher": "Test Publisher Inc",
            },
            {
                "journal_name": "Test Journal Beta",
                "normalized_name": "test_journal_beta",
                "issn": "2345-6789",
                "publisher": "Beta Publishers",
            },
        ]

        # Perform the write operation
        result = db_writer._batch_write_journals(
            "test_source", AssessmentType.PREDATORY, test_journals
        )

        assert result["total_records"] == 2
        assert result["unique_journals"] == 2
        assert result["duplicates"] == 0

        # Verify data persistence using JournalCache
        journal_cache = JournalCache(db_path=temp_db)

        # Check journals were stored
        all_journals = journal_cache.search_journals()
        assert len(all_journals) == 2

        # Check specific journal data
        alpha_journals = journal_cache.search_journals(
            normalized_name="test_journal_alpha"
        )
        assert len(alpha_journals) == 1
        alpha = alpha_journals[0]
        assert alpha["display_name"] == "Test Journal Alpha"
        assert alpha["issn"] == "1234-5678"
        assert alpha["eissn"] == "1234-5679"
        assert alpha["publisher"] == "Test Publisher Inc"

        # Verify assessments were created
        for normalized_name in ["test_journal_alpha", "test_journal_beta"]:
            journals = journal_cache.search_journals(normalized_name=normalized_name)
            assert len(journals) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_foreign_key_constraints(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test that foreign key constraints are properly enforced."""
        test_journals = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            }
        ]

        # Perform the write operation
        db_writer._batch_write_journals(
            "test_source", AssessmentType.PREDATORY, test_journals
        )

        # Verify foreign key relationships
        with sqlite3.connect(temp_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Get journal_id and source_id
            cursor.execute(
                "SELECT id FROM journals WHERE normalized_name = ?", ("test_journal",)
            )
            journal_id = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id FROM data_sources WHERE name = ?", ("test_source",)
            )
            source_id = cursor.fetchone()[0]

            # Verify journal_names has correct foreign key
            cursor.execute(
                "SELECT journal_id FROM journal_names WHERE name = ?",
                ("Test Journal",),
            )
            assert cursor.fetchone()[0] == journal_id

            # Verify source_assessments has correct foreign keys
            cursor.execute(
                "SELECT journal_id, source_id FROM source_assessments WHERE journal_id = ?",
                (journal_id,),
            )
            row = cursor.fetchone()
            assert row[0] == journal_id
            assert row[1] == source_id

            # Test cascade delete - deleting journal should delete related records
            cursor.execute("DELETE FROM journals WHERE id = ?", (journal_id,))
            conn.commit()

            # Verify cascade delete worked
            cursor.execute(
                "SELECT COUNT(*) FROM journal_names WHERE journal_id = ?", (journal_id,)
            )
            assert cursor.fetchone()[0] == 0

            cursor.execute(
                "SELECT COUNT(*) FROM source_assessments WHERE journal_id = ?",
                (journal_id,),
            )
            assert cursor.fetchone()[0] == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_sync_operations_data_integrity(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test data integrity across multiple sync operations."""
        # First sync operation
        first_batch = [
            {
                "journal_name": "Journal One",
                "normalized_name": "journal_one",
                "issn": "1111-1111",
            },
            {
                "journal_name": "Journal Two",
                "normalized_name": "journal_two",
                "issn": "2222-2222",
            },
        ]

        result1 = db_writer._batch_write_journals(
            "source_one", AssessmentType.PREDATORY, first_batch
        )
        assert result1["unique_journals"] == 2

        # Second sync operation with overlapping data (upsert test)
        second_batch = [
            {
                "journal_name": "Journal One Updated",  # Updated display name
                "normalized_name": "journal_one",  # Same normalized name
                "issn": "1111-1111",
                "publisher": "New Publisher",  # Added publisher
            },
            {
                "journal_name": "Journal Three",
                "normalized_name": "journal_three",
                "issn": "3333-3333",
            },
        ]

        result2 = db_writer._batch_write_journals(
            "source_two", AssessmentType.LEGITIMATE, second_batch
        )
        assert result2["unique_journals"] == 2

        # Verify data integrity after multiple syncs using JournalCache
        journal_cache = JournalCache(db_path=temp_db)

        # Should have 3 unique journals (one, two, three)
        all_journals = journal_cache.search_journals()
        assert len(all_journals) == 3

        # Journal One should be updated with new data
        journal_one = journal_cache.search_journals(normalized_name="journal_one")
        assert len(journal_one) == 1
        assert journal_one[0]["display_name"] == "Journal One Updated"
        assert journal_one[0]["publisher"] == "New Publisher"

        # Journal One should have assessments from both sources
        # Use raw SQL only for multi-table assessment verification (not abstracted by cache)
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT ds.name, sa.assessment FROM source_assessments sa
                   JOIN journals j ON sa.journal_id = j.id
                   JOIN data_sources ds ON sa.source_id = ds.id
                   WHERE j.normalized_name = ?
                   ORDER BY ds.name""",
                ("journal_one",),
            )
            assessments = cursor.fetchall()
            assert len(assessments) == 2
            assert ("source_one", AssessmentType.PREDATORY.value) in assessments
            assert ("source_two", AssessmentType.LEGITIMATE.value) in assessments

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_url_deduplication_and_persistence(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test that URLs are properly deduplicated and persisted."""
        test_journals = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "urls": ["https://example.com", "https://example.org"],
                "metadata": {
                    "website_url": "https://example.com",  # Duplicate
                    "source_url": "https://source.example.net",
                },
            }
        ]

        db_writer._batch_write_journals(
            "test_source", AssessmentType.PREDATORY, test_journals
        )

        # Verify URL deduplication using JournalCache
        journal_cache = JournalCache(db_path=temp_db)
        journals = journal_cache.search_journals(normalized_name="test_journal")
        assert len(journals) == 1

        urls = journals[0].get("urls", [])
        # Should have 3 unique URLs (duplicate removed)
        assert len(urls) == 3
        assert "https://example.com" in urls
        assert "https://example.org" in urls
        assert "https://source.example.net" in urls

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unique_constraint_enforcement(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test that unique constraints are properly enforced."""
        test_journals = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            }
        ]

        # First write
        db_writer._batch_write_journals(
            "test_source", AssessmentType.PREDATORY, test_journals
        )

        # Verify only one journal entry exists using JournalCache
        journal_cache = JournalCache(db_path=temp_db)
        journals = journal_cache.search_journals(normalized_name="test_journal")
        assert len(journals) == 1

        # Test unique constraint enforcement at database level
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            # Try to manually insert duplicate (should fail due to UNIQUE constraint)
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)",
                    ("test_journal", "Duplicate Journal"),
                )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test that database transaction is rolled back on error."""
        # Create invalid journal data that will cause an error
        test_journals = [
            {
                "journal_name": "Valid Journal",
                "normalized_name": "valid_journal",
            },
            {
                "journal_name": "Invalid Journal",
                # Missing normalized_name will be skipped, but we'll cause an error differently
            },
        ]

        # Patch _execute_batch_inserts to raise an error mid-transaction
        original_method = db_writer._execute_batch_inserts

        def failing_batch_insert(*args, **kwargs):
            # Insert some data first
            original_method(*args, **kwargs)
            # Then raise an error
            raise sqlite3.Error("Simulated database error")

        with (
            patch.object(
                db_writer,
                "_execute_batch_inserts",
                side_effect=failing_batch_insert,
            ),
            pytest.raises(sqlite3.Error),
        ):
            db_writer._batch_write_journals(
                "test_source", AssessmentType.PREDATORY, test_journals
            )

        # Verify rollback: no journals should be in database
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM journals")
            # Transaction should have been rolled back
            assert cursor.fetchone()[0] == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_async_queue_with_real_database(
        self, temp_db: Path, db_writer: AsyncDBWriter, mock_data_source_manager
    ) -> None:
        """Test async queue operations with real database writes."""
        test_journals = [
            {
                "journal_name": "Async Test Journal",
                "normalized_name": "async_test_journal",
                "issn": "9999-9999",
            }
        ]

        # Start the async writer
        await db_writer.start_writer()

        # Queue multiple write operations
        await db_writer.queue_write("source_1", AssessmentType.PREDATORY, test_journals)
        await db_writer.queue_write(
            "source_2", AssessmentType.LEGITIMATE, test_journals
        )

        # Give time for processing
        await asyncio.sleep(0.2)

        # Stop the writer
        await db_writer.stop_writer()

        # Verify both syncs were processed using cache classes
        journal_cache = JournalCache(db_path=temp_db)

        # Should have 1 journal
        journals = journal_cache.search_journals()
        assert len(journals) == 1

        # Use raw SQL for counts not provided by cache API
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()

            # Should have 2 sources
            cursor.execute("SELECT COUNT(*) FROM data_sources")
            assert cursor.fetchone()[0] == 2

            # Should have 2 assessments (one from each source)
            cursor.execute("SELECT COUNT(*) FROM source_assessments")
            assert cursor.fetchone()[0] == 2
