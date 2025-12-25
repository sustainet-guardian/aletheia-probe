# SPDX-License-Identifier: MIT
"""Tests for the cache assessment module."""

import json
import tempfile
import threading
from pathlib import Path

import pytest

from aletheia_probe.cache import DataSourceManager, JournalCache
from aletheia_probe.cache.schema import init_database
from aletheia_probe.data_models import JournalEntryData
from aletheia_probe.enums import AssessmentType


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    cache = JournalCache(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestCacheJournal:
    """Test cases for CacheJournal."""

    def test_add_journal_entry(self, temp_cache):
        """Test adding journal entries."""
        # Register data source
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("test_source", "Test Source", "predatory")

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test journal",
            issn="1234-5678",
            eissn="0028-0836",  # Nature's ISSN - valid checksum
            publisher="Test Publisher",
            metadata={"key": "value"},
        )
        temp_cache.add_journal_entry(entry)

        # Verify entry was added using the cache API
        results = temp_cache.search_journals(normalized_name="test journal")
        assert len(results) == 1

        journal = results[0]
        assert journal["normalized_name"] == "test journal"
        assert journal["display_name"] == "Test Journal"
        assert journal["issn"] == "1234-5678"
        assert journal["eissn"] == "0028-0836"
        assert journal["publisher"] == "Test Publisher"

        # Verify source-specific data by searching with source_name
        source_results = temp_cache.search_journals(
            source_name="test_source", normalized_name="test journal"
        )
        assert len(source_results) == 1

        source_journal = source_results[0]
        assert source_journal["journal_name"] == "Test Journal"
        assert source_journal["list_type"] == "predatory"
        assert json.loads(source_journal["metadata"]) == {"key": "value"}

    def test_search_journals_basic(self, temp_cache):
        """Test basic journal search functionality."""
        # Register data source
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("test_source", "Test Source", "predatory")

        # Add test data
        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal of Computer Science",
            normalized_name="journal of computer science",
        )
        temp_cache.add_journal_entry(entry)

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
        # Register data source
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("test_source", "Test Source", "legitimate")

        # Add test data
        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Nature",
            normalized_name="nature",
            issn="0028-0836",
        )
        temp_cache.add_journal_entry(entry)

        # Search by ISSN
        results = temp_cache.search_journals(issn="0028-0836")
        assert len(results) == 1
        assert results[0]["issn"] == "0028-0836"
        assert results[0]["display_name"] == "Nature"

    def test_search_journals_by_source(self, temp_cache):
        """Test searching journals by source."""
        # Register data sources
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("bealls", "Bealls List", "predatory")
        dsm.register_data_source("doaj", "DOAJ", "legitimate")

        # Add test data from different sources
        entry1 = JournalEntryData(
            source_name="bealls",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.add_journal_entry(entry1)
        entry2 = JournalEntryData(
            source_name="doaj",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Journal B",
            normalized_name="journal b",
        )
        temp_cache.add_journal_entry(entry2)

        # Search by source
        bealls_results = temp_cache.search_journals(source_name="bealls")
        doaj_results = temp_cache.search_journals(source_name="doaj")

        assert len(bealls_results) == 1
        assert len(doaj_results) == 1
        # When searching by source_name, results include the journal_name field
        assert bealls_results[0]["journal_name"] == "Journal A"
        assert doaj_results[0]["journal_name"] == "Journal B"

    def test_search_journals_by_list_type(self, temp_cache):
        """Test searching journals by list type."""
        # Register data source
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("test_source", "Test Source", "mixed")

        # Add test data
        entry1 = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Predatory Journal",
            normalized_name="predatory journal",
        )
        temp_cache.add_journal_entry(entry1)
        entry2 = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Legitimate Journal",
            normalized_name="legitimate journal",
        )
        temp_cache.add_journal_entry(entry2)

        # Search by assessment (list_type maps to assessment in normalized schema)
        predatory_results = temp_cache.search_journals(
            source_name="test_source", assessment="predatory"
        )
        legitimate_results = temp_cache.search_journals(
            source_name="test_source", assessment="legitimate"
        )

        assert len(predatory_results) == 1
        assert len(legitimate_results) == 1
        # With source_name, results include the source-specific list_type field
        assert predatory_results[0]["list_type"] == "predatory"
        assert legitimate_results[0]["list_type"] == "legitimate"


class TestCacheJournalAdditional:
    """Additional test cases for JournalCache functionality."""

    def test_cache_with_metadata(self, temp_cache):
        """Test caching journal entries with metadata."""
        # Register data source
        dsm = DataSourceManager(temp_cache.db_path)
        dsm.register_data_source("test_source", "Test Source", "legitimate")

        metadata = {
            "impact_factor": 2.5,
            "categories": ["Computer Science", "AI"],
            "open_access": True,
        }

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="AI Journal",
            normalized_name="ai journal",
            metadata=metadata,
        )
        temp_cache.add_journal_entry(entry)

        # Search by source to get back source-specific metadata
        results = temp_cache.search_journals(
            source_name="test_source", normalized_name="ai journal"
        )
        assert len(results) == 1

        # Metadata should be stored as JSON and retrievable
        result_metadata = results[0]["metadata"]
        assert result_metadata is not None

    def test_concurrent_cache_access(self, temp_cache):
        """Test that cache handles concurrent access properly."""
        # Register data sources for all threads
        dsm = DataSourceManager(temp_cache.db_path)
        for i in range(3):
            dsm.register_data_source(f"source_{i}", f"Source {i}", "predatory")

        def add_entries(source_suffix):
            for i in range(10):
                entry = JournalEntryData(
                    source_name=f"source_{source_suffix}",
                    assessment=AssessmentType.PREDATORY,
                    journal_name=f"Journal {source_suffix}_{i}",
                    normalized_name=f"journal {source_suffix} {i}",
                )
                temp_cache.add_journal_entry(entry)

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


class TestCacheManagerWithJournalEntryData:
    """Test CacheManager functionality using JournalEntryData dataclass."""

    def test_add_journal_entry_with_invalid_entry_type(self, temp_cache):
        """Test that invalid entry type raises TypeError."""
        with pytest.raises(TypeError):
            temp_cache.add_journal_entry("invalid_entry")

    def test_add_journal_entry_validation_errors(self, temp_cache):
        """Test validation error handling for required fields."""
        # Pydantic validates required fields when creating JournalEntryData
        # Test missing source_name
        with pytest.raises(ValueError):
            JournalEntryData(
                source_name="",
                assessment=AssessmentType.PREDATORY,
                journal_name="Test Journal",
                normalized_name="test_journal",
            )

        # Test missing journal_name
        with pytest.raises(ValueError):
            JournalEntryData(
                source_name="test_source",
                assessment=AssessmentType.PREDATORY,
                journal_name="",
                normalized_name="test_journal",
            )

        # Test missing normalized_name
        with pytest.raises(ValueError):
            JournalEntryData(
                source_name="test_source",
                assessment=AssessmentType.PREDATORY,
                journal_name="Test Journal",
                normalized_name="",
            )

    def test_add_journal_entry_unregistered_source(self, temp_cache):
        """Test adding journal entry with unregistered source raises error."""
        entry = JournalEntryData(
            source_name="unregistered_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test_journal",
        )

        with pytest.raises(ValueError, match="Source.*not registered"):
            temp_cache.add_journal_entry(entry)
