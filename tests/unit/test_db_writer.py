# SPDX-License-Identifier: MIT
"""Tests for the AsyncDBWriter class."""

import asyncio
import sqlite3
from unittest.mock import Mock, patch

import pytest

from aletheia_probe.cache import DataSourceManager
from aletheia_probe.cache.schema import init_database
from aletheia_probe.cache_sync import AsyncDBWriter
from aletheia_probe.data_models import JournalDataDict


class TestAsyncDBWriter:
    """Test cases for AsyncDBWriter."""

    @pytest.fixture
    def memory_db(self, tmp_path):
        """Create a temporary database file with initialized schema.

        Using a file-based database instead of :memory: because SQLite's
        :memory: databases are not shared between connections, which causes
        issues when testing database operations that open new connections.
        """
        db_path = tmp_path / "test_db.sqlite"
        init_database(db_path)
        return db_path

    @pytest.fixture
    def db_writer(self):
        """Create AsyncDBWriter instance for testing."""
        return AsyncDBWriter()

    @pytest.mark.asyncio
    async def test_start_writer(self, db_writer):
        """Test starting the database writer task."""
        assert db_writer.writer_task is None

        await db_writer.start_writer()

        assert db_writer.writer_task is not None
        assert not db_writer.writer_task.done()

        # Clean up
        await db_writer.stop_writer()

    @pytest.mark.asyncio
    async def test_start_writer_already_started(self, db_writer):
        """Test starting writer when already started."""
        await db_writer.start_writer()
        first_task = db_writer.writer_task

        # Start again - should not create a new task
        await db_writer.start_writer()
        second_task = db_writer.writer_task

        assert first_task is second_task

        # Clean up
        await db_writer.stop_writer()

    @pytest.mark.asyncio
    async def test_stop_writer(self, db_writer):
        """Test stopping the database writer task."""
        await db_writer.start_writer()
        assert db_writer.writer_task is not None

        await db_writer.stop_writer()

        assert db_writer.writer_task is None

    @pytest.mark.asyncio
    async def test_stop_writer_not_started(self, db_writer):
        """Test stopping writer when not started."""
        assert db_writer.writer_task is None

        # Should not raise an error
        await db_writer.stop_writer()

        assert db_writer.writer_task is None

    @pytest.mark.asyncio
    async def test_queue_write(self, db_writer):
        """Test queuing data for writing."""
        test_journals: list[JournalDataDict] = [
            {"journal_name": "Test Journal", "normalized_name": "test_journal"}
        ]

        # Start the writer
        await db_writer.start_writer()

        # Queue some data
        await db_writer.queue_write("test_source", "predatory", test_journals)

        # Verify data was queued
        assert not db_writer.write_queue.empty()

        # Clean up
        await db_writer.stop_writer()

    @pytest.mark.asyncio
    async def test_db_writer_loop_with_mock_data(self, db_writer):
        """Test the database writer loop with mocked data."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test_journal_1",
                "issn": "1234-5678",
                "eissn": "1234-5679",
                "publisher": "Test Publisher",
            }
        ]

        with (
            patch.object(
                db_writer,
                "_batch_write_journals",
                return_value={
                    "total_records": 1,
                    "unique_journals": 1,
                    "duplicates": 0,
                },
            ) as mock_batch_write,
            patch(
                "aletheia_probe.cache_sync.db_writer.DataSourceManager"
            ) as mock_get_cache_manager,
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.log_update = Mock()

            # Start writer
            await db_writer.start_writer()

            # Queue data
            await db_writer.queue_write("test_source", "predatory", test_journals)

            # Give the loop a moment to process
            await asyncio.sleep(0.1)

            # Stop writer (this processes the queue)
            await db_writer.stop_writer()

            # Verify batch write was called
            mock_batch_write.assert_called_once_with(
                "test_source", "predatory", test_journals
            )
            mock_cache_manager.log_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_writer_loop_database_error(self, db_writer):
        """Test database writer loop with database error."""
        test_journals: list[JournalDataDict] = [
            {"journal_name": "Test", "normalized_name": "test"}
        ]

        with patch.object(
            db_writer,
            "_batch_write_journals",
            side_effect=sqlite3.Error("Database error"),
        ):
            # Start writer
            await db_writer.start_writer()

            # Queue data that will cause an error
            await db_writer.queue_write("error_source", "predatory", test_journals)

            # Give the loop a moment to process
            await asyncio.sleep(0.1)

            # Stop writer
            await db_writer.stop_writer()

            # The error should be handled gracefully (not crash the test)

    @pytest.mark.asyncio
    async def test_batch_write_journals(self, db_writer, memory_db):
        """Test batch writing of journals."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test_journal_1",
                "issn": "1234-5678",
                "eissn": "1234-5679",
                "publisher": "Test Publisher",
            },
            {
                "journal_name": "Test Journal 2",
                "normalized_name": "test_journal_2",
                "issn": "2345-6789",
                "publisher": "Another Publisher",
            },
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            result = db_writer._batch_write_journals(
                "test_source", "predatory", test_journals
            )

            assert result["total_records"] == 2
            assert result["unique_journals"] == 2
            assert result["duplicates"] == 0

        # Verify data was actually written to database
        with sqlite3.connect(memory_db) as conn:
            cursor = conn.cursor()

            # Check journals were created
            cursor.execute("SELECT COUNT(*) FROM journals")
            assert cursor.fetchone()[0] == 2

            # Check source was created
            cursor.execute("SELECT COUNT(*) FROM data_sources WHERE name = ?", ("test_source",))
            assert cursor.fetchone()[0] == 1

            # Check assessments were created
            cursor.execute("SELECT COUNT(*) FROM source_assessments")
            assert cursor.fetchone()[0] == 2

    @pytest.mark.asyncio
    async def test_batch_write_journals_new_source(self, db_writer, memory_db):
        """Test batch writing with new source that needs registration."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            }
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            result = db_writer._batch_write_journals(
                "new_source", "predatory", test_journals
            )

            assert result["total_records"] == 1
            assert result["unique_journals"] == 1

        # Verify source was registered in the database
        with sqlite3.connect(memory_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, source_type FROM data_sources WHERE name = ?",
                ("new_source",)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "new_source"
            assert row[1] == "predatory"

    @pytest.mark.asyncio
    async def test_batch_write_journals_with_duplicates(self, db_writer, memory_db):
        """Test batch writing with duplicate journals."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            },
            {
                "journal_name": "Test Journal Same",  # Different name but same normalized
                "normalized_name": "test_journal",  # Same normalized name
                "issn": "1234-5679",
            },
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            result = db_writer._batch_write_journals(
                "test_source", "predatory", test_journals
            )

            # Should have 2 total records but only 1 unique journal
            assert result["total_records"] == 2
            assert result["unique_journals"] == 1
            assert result["duplicates"] == 1

        # Verify only one journal entry in database (deduplication worked)
        with sqlite3.connect(memory_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM journals WHERE normalized_name = ?", ("test_journal",))
            assert cursor.fetchone()[0] == 1

    @pytest.mark.asyncio
    async def test_batch_write_journals_skip_invalid_entries(self, db_writer, memory_db):
        """Test batch writing skips entries without normalized_name."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Valid Journal",
                "normalized_name": "valid_journal",
                "issn": "1234-5678",
            },
            {
                "journal_name": "Invalid Journal",
                # Missing normalized_name
                "issn": "2345-6789",
            },  # type: ignore[typeddict-item]
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            result = db_writer._batch_write_journals(
                "test_source", "predatory", test_journals
            )

            # Should only process the valid journal
            assert result["total_records"] == 1
            assert result["unique_journals"] == 1

        # Verify only valid journal was written
        with sqlite3.connect(memory_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT normalized_name FROM journals")
            journals = cursor.fetchall()
            assert len(journals) == 1
            assert journals[0][0] == "valid_journal"

    @pytest.mark.asyncio
    async def test_cascade_delete_behavior(self, db_writer, memory_db):
        """Test that cascade deletes work correctly with real database."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            }
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            db_writer._batch_write_journals("test_source", "predatory", test_journals)

        # Verify data was written
        with sqlite3.connect(memory_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Get journal_id
            cursor.execute(
                "SELECT id FROM journals WHERE normalized_name = ?", ("test_journal",)
            )
            journal_id = cursor.fetchone()[0]

            # Verify related records exist
            cursor.execute(
                "SELECT COUNT(*) FROM journal_names WHERE journal_id = ?", (journal_id,)
            )
            assert cursor.fetchone()[0] > 0

            cursor.execute(
                "SELECT COUNT(*) FROM source_assessments WHERE journal_id = ?",
                (journal_id,),
            )
            assert cursor.fetchone()[0] > 0

            # Delete journal and verify cascade
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

    @pytest.mark.asyncio
    async def test_unique_constraint_enforcement(self, db_writer, memory_db):
        """Test that unique constraints prevent duplicate normalized names."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal",
                "normalized_name": "test_journal",
                "issn": "1234-5678",
            }
        ]

        with patch(
            "aletheia_probe.cache_sync.db_writer.DataSourceManager"
        ) as mock_dsm_class:
            mock_dsm = DataSourceManager()
            mock_dsm.db_path = memory_db
            mock_dsm_class.return_value = mock_dsm

            db_writer._batch_write_journals("test_source", "predatory", test_journals)

        # Verify only one journal exists
        with sqlite3.connect(memory_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM journals WHERE normalized_name = ?", ("test_journal",))
            assert cursor.fetchone()[0] == 1

            # Try to manually insert duplicate (should fail)
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO journals (normalized_name, display_name) VALUES (?, ?)",
                    ("test_journal", "Duplicate Journal"),
                )

    @pytest.mark.asyncio
    async def test_db_writer_loop_with_duplicates_reporting(self, db_writer):
        """Test the database writer loop reports duplicates correctly."""
        test_journals: list[JournalDataDict] = [
            {
                "journal_name": "Test Journal 1",
                "normalized_name": "test_journal_1",
                "issn": "1234-5678",
            }
        ]

        with (
            patch.object(
                db_writer,
                "_batch_write_journals",
                return_value={
                    "total_records": 5,
                    "unique_journals": 3,
                    "duplicates": 2,  # This will trigger the duplicates > 0 branch
                },
            ) as mock_batch_write,
            patch(
                "aletheia_probe.cache_sync.db_writer.DataSourceManager"
            ) as mock_get_cache_manager,
        ):
            mock_cache_manager = Mock()
            mock_get_cache_manager.return_value = mock_cache_manager
            mock_cache_manager.log_update = Mock()

            # Start writer
            await db_writer.start_writer()

            # Queue data
            await db_writer.queue_write("test_source", "predatory", test_journals)

            # Give the loop a moment to process
            await asyncio.sleep(0.1)

            # Stop writer
            await db_writer.stop_writer()

            # Verify the duplicates branch was covered
            mock_batch_write.assert_called_once()
            mock_cache_manager.log_update.assert_called_once()
