# SPDX-License-Identifier: MIT
"""Tests for the cache management module."""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.cache import CacheManager
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    QueryInput,
)


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    cache = CacheManager(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


@pytest.fixture
def sample_assessment_result():
    """Sample assessment result for testing."""
    return AssessmentResult(
        input_query="Test Journal",
        assessment="predatory",
        confidence=0.85,
        overall_score=0.9,
        backend_results=[
            BackendResult(
                backend_name="test_backend",
                status=BackendStatus.FOUND,
                confidence=0.8,
                assessment="predatory",
                data={"key": "value"},
                sources=["test_source"],
                response_time=0.1,
            )
        ],
        metadata=None,
        reasoning=["Found in predatory list"],
        processing_time=1.5,
    )


class TestCacheManager:
    """Test cases for CacheManager."""

    def test_init_cache(self, temp_cache):
        """Test cache initialization creates proper tables."""
        # Check that tables exist
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.cursor()

            # Check assessment_cache table
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='assessment_cache'
            """
            )
            assert cursor.fetchone() is not None

            # Check normalized tables
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='journals'
            """
            )
            assert cursor.fetchone() is not None

            # Check data_sources table
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='data_sources'
            """
            )
            assert cursor.fetchone() is not None

    def test_store_and_get_assessment(self, temp_cache, sample_assessment_result):
        """Test storing and retrieving assessment results."""
        query_hash = "test_hash"

        # Store assessment
        temp_cache.cache_assessment_result(
            query_hash, "Test Journal", sample_assessment_result
        )

        # Retrieve assessment
        retrieved = temp_cache.get_cached_assessment(query_hash)

        assert retrieved is not None
        assert retrieved.input_query == sample_assessment_result.input_query
        assert retrieved.assessment == sample_assessment_result.assessment
        assert retrieved.confidence == sample_assessment_result.confidence

    def test_get_assessment_nonexistent(self, temp_cache):
        """Test retrieving non-existent assessment."""
        result = temp_cache.get_cached_assessment("nonexistent_hash")
        assert result is None

    def test_get_assessment_expired(self, temp_cache, sample_assessment_result):
        """Test that expired assessments are not returned."""
        query_hash = "expired_hash"

        # Store with negative TTL (already expired)
        temp_cache.cache_assessment_result(
            query_hash, "Test Journal", sample_assessment_result, ttl_hours=-1
        )

        result = temp_cache.get_cached_assessment(query_hash)
        assert result is None

    def test_add_journal_entry(self, temp_cache):
        """Test adding journal entries."""
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Test Journal",
            normalized_name="test journal",
            issn="1234-5678",
            eissn="0028-0836",  # Nature's ISSN - valid checksum
            publisher="Test Publisher",
            metadata={"key": "value"},
        )

        # Verify entry was added to normalized tables
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.cursor()

            # Check that the journal was added to the journals table
            cursor.execute(
                "SELECT * FROM journals WHERE normalized_name = ?", ("test journal",)
            )
            journal_result = cursor.fetchone()
            assert journal_result is not None
            assert journal_result[1] == "test journal"  # normalized_name column
            assert journal_result[2] == "Test Journal"  # display_name column
            assert journal_result[3] == "1234-5678"  # issn column
            assert journal_result[4] == "0028-0836"  # eissn column
            assert journal_result[5] == "Test Publisher"  # publisher column

            # Check that the journal name was added
            cursor.execute(
                "SELECT * FROM journal_names WHERE name = ?", ("Test Journal",)
            )
            name_result = cursor.fetchone()
            assert name_result is not None
            assert name_result[2] == "Test Journal"  # name column

            # Check that the source assessment was added
            cursor.execute(
                """SELECT sa.assessment FROM source_assessments sa
                   JOIN data_sources ds ON sa.source_id = ds.id
                   WHERE ds.name = ? AND sa.journal_id = ?""",
                ("test_source", journal_result[0]),
            )
            assessment_result = cursor.fetchone()
            assert assessment_result is not None
            assert assessment_result[0] == "predatory"

    def test_search_journals_basic(self, temp_cache):
        """Test basic journal search functionality."""
        # Add test data
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Journal of Computer Science",
            normalized_name="journal of computer science",
        )

        # Search by normalized name
        results = temp_cache.search_journals(
            normalized_name="journal of computer science"
        )
        assert len(results) == 1
        # The new implementation uses 'display_name' field
        assert results[0]["display_name"] == "Journal of Computer Science"
        assert results[0]["normalized_name"] == "journal of computer science"

    def test_search_journals_by_issn(self, temp_cache):
        """Test searching journals by ISSN."""
        # Add test data
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="legitimate",
            journal_name="Nature",
            normalized_name="nature",  # Required parameter
            issn="0028-0836",
        )

        # Search by ISSN
        results = temp_cache.search_journals(issn="0028-0836")
        assert len(results) == 1
        assert results[0]["issn"] == "0028-0836"
        assert results[0]["display_name"] == "Nature"

    def test_search_journals_by_source(self, temp_cache):
        """Test searching journals by source."""
        # Add test data from different sources
        temp_cache.add_journal_list_entry(
            source_name="bealls",
            list_type="predatory",
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_list_entry(
            source_name="doaj",
            list_type="legitimate",
            journal_name="Journal B",
            normalized_name="journal b",
        )

        # Search by source
        bealls_results = temp_cache.search_journals(source_name="bealls")
        doaj_results = temp_cache.search_journals(source_name="doaj")

        assert len(bealls_results) == 1
        assert len(doaj_results) == 1
        # When searching by source_name, backward compatibility provides journal_name
        assert bealls_results[0]["journal_name"] == "Journal A"
        assert doaj_results[0]["journal_name"] == "Journal B"

    def test_search_journals_by_list_type(self, temp_cache):
        """Test searching journals by list type."""
        # Add test data
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Predatory Journal",
            normalized_name="predatory journal",
        )
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="legitimate",
            journal_name="Legitimate Journal",
            normalized_name="legitimate journal",
        )

        # Search by assessment (list_type maps to assessment in normalized schema)
        predatory_results = temp_cache.search_journals(
            source_name="test_source", assessment="predatory"
        )
        legitimate_results = temp_cache.search_journals(
            source_name="test_source", assessment="legitimate"
        )

        assert len(predatory_results) == 1
        assert len(legitimate_results) == 1
        # With source_name, backward compatibility provides list_type field
        assert predatory_results[0]["list_type"] == "predatory"
        assert legitimate_results[0]["list_type"] == "legitimate"

    def test_clear_source_data(self, temp_cache):
        """Test clearing data for a specific source."""
        # Add test data from multiple sources
        temp_cache.add_journal_list_entry(
            source_name="source_to_clear",
            list_type="predatory",
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_list_entry(
            source_name="source_to_keep",
            list_type="legitimate",
            journal_name="Journal B",
            normalized_name="journal b",
        )

        # Clear one source
        cleared_count = temp_cache.remove_source_data("source_to_clear")

        assert cleared_count == 1

        # Verify correct data was cleared
        remaining_results = temp_cache.search_journals(source_name="source_to_keep")
        assert len(remaining_results) == 1
        assert remaining_results[0]["journal_name"] == "Journal B"

    def test_cleanup_expired_cache(self, temp_cache, sample_assessment_result):
        """Test cleanup of expired cache entries."""
        # Add entries with different expiration times
        temp_cache.cache_assessment_result(
            "recent_hash", "Test Journal", sample_assessment_result, ttl_hours=24
        )
        temp_cache.cache_assessment_result(
            "old_hash",
            "Test Journal",
            sample_assessment_result,
            ttl_hours=-1,  # Already expired
        )

        # Cleanup
        expired_count = temp_cache.cleanup_expired_cache()

        assert expired_count >= 1  # At least the expired one

        # Verify cleanup worked
        recent_result = temp_cache.get_cached_assessment("recent_hash")
        old_result = temp_cache.get_cached_assessment("old_hash")

        assert recent_result is not None
        assert old_result is None

    def test_has_source_data(self, temp_cache):
        """Test checking if source has data."""
        # Initially no data
        assert not temp_cache.has_source_data("test_source")

        # Add data
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Test Journal",
            normalized_name="test journal",
        )

        # Should now have data
        assert temp_cache.has_source_data("test_source")

    def test_get_source_last_updated(self, temp_cache):
        """Test getting source last updated timestamp."""
        source_name = "test_source"

        # Initially no update time
        last_updated = temp_cache.get_source_last_updated(source_name)
        assert last_updated is None

        # Register the source first (required for log_update in normalized schema)
        temp_cache.register_data_source(source_name, "Test Source", "mixed")

        # Log an update
        temp_cache.log_update(source_name, "manual", "success", records_added=5)

        # Should now have update time
        last_updated = temp_cache.get_source_last_updated(source_name)
        assert isinstance(last_updated, datetime)

    def test_get_source_stats(self, temp_cache):
        """Test getting source statistics."""
        # Add test data
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="predatory",
            journal_name="Journal B",
            normalized_name="journal b",
        )
        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="legitimate",
            journal_name="Journal C",
            normalized_name="journal c",
        )

        stats = temp_cache.get_source_stats()

        assert "test_source" in stats
        source_stats = stats["test_source"]
        assert source_stats["total"] == 3
        assert source_stats["lists"]["predatory"]["count"] == 2
        assert source_stats["lists"]["legitimate"]["count"] == 1

    def test_remove_source_data(self, temp_cache):
        """Test removing all data for a source."""
        # Add test data
        temp_cache.add_journal_list_entry(
            source_name="source_to_remove",
            list_type="predatory",
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_list_entry(
            source_name="source_to_remove",
            list_type="legitimate",
            journal_name="Journal B",
            normalized_name="journal b",
        )

        # Remove source data
        removed_count = temp_cache.remove_source_data("source_to_remove")

        assert removed_count == 2

        # Verify data is gone
        results = temp_cache.search_journals(source_name="source_to_remove")
        assert len(results) == 0

    def test_get_available_sources(self, temp_cache):
        """Test getting list of available sources."""
        # Initially empty
        sources = temp_cache.get_available_sources()
        assert len(sources) == 0

        # Add data from multiple sources
        temp_cache.add_journal_list_entry(
            source_name="source1",
            list_type="predatory",
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_list_entry(
            source_name="source2",
            list_type="legitimate",
            journal_name="Journal B",
            normalized_name="journal b",
        )

        # Should now have sources
        sources = temp_cache.get_available_sources()
        assert "source1" in sources
        assert "source2" in sources

    def test_log_update(self, temp_cache):
        """Test logging data source updates."""
        # First register the data source
        temp_cache.register_data_source("test_source", "Test Source", "predatory")

        temp_cache.log_update("test_source", "full", "success", records_added=100)

        # Verify log entry in the new source_updates table
        with sqlite3.connect(temp_cache.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT su.*, ds.name FROM source_updates su
                JOIN data_sources ds ON su.source_id = ds.id
                WHERE ds.name = ? AND su.status = ?
                ORDER BY su.completed_at DESC LIMIT 1
            """,
                ("test_source", "success"),
            )

            result = cursor.fetchone()
            assert result is not None
            assert result[-1] == "test_source"  # ds.name (last column)
            assert result[3] == "success"  # status
            assert result[4] == 100  # records_added

    def test_cache_with_metadata(self, temp_cache):
        """Test caching journal entries with metadata."""
        metadata = {
            "impact_factor": 2.5,
            "categories": ["Computer Science", "AI"],
            "open_access": True,
        }

        temp_cache.add_journal_list_entry(
            source_name="test_source",
            list_type="legitimate",
            journal_name="AI Journal",
            normalized_name="ai journal",
            metadata=metadata,
        )

        # Search by source to get back metadata in backward compatibility format
        results = temp_cache.search_journals(
            source_name="test_source", normalized_name="ai journal"
        )
        assert len(results) == 1

        # Metadata should be stored as JSON and retrievable
        result_metadata = results[0]["metadata"]
        assert result_metadata is not None

    def test_concurrent_cache_access(self, temp_cache):
        """Test that cache handles concurrent access properly."""
        import threading

        def add_entries(source_suffix):
            for i in range(10):
                temp_cache.add_journal_list_entry(
                    source_name=f"source_{source_suffix}",
                    list_type="predatory",
                    journal_name=f"Journal {source_suffix}_{i}",
                    normalized_name=f"journal {source_suffix} {i}",
                )

        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=add_entries, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify all entries were added by checking each source
        total_count = 0
        for i in range(3):
            source_results = temp_cache.search_journals(source_name=f"source_{i}")
            total_count += len(source_results)

        assert total_count == 30  # 3 sources * 10 entries each
