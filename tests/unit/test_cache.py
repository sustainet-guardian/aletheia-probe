# SPDX-License-Identifier: MIT
"""Integration tests for multiple cache components working together.

This file contains tests that verify the interaction between multiple cache classes.
For single-component tests, see the individual test files:
- test_cache_journals.py - JournalCache only
- test_cache_acronym.py - AcronymCache only
- test_cache_assessment.py - AssessmentCache only
- test_cache_retraction.py - RetractionCache only
- test_cache_key_value.py - KeyValueCache only
- test_cache_data_source.py - DataSourceManager only
- test_cache_schema.py - Database schema initialization
"""

import hashlib
import json
import logging
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from aletheia_probe.cache import (
    AcronymCache,
    AssessmentCache,
    DataSourceManager,
    JournalCache,
    KeyValueCache,
    RetractionCache,
)
from aletheia_probe.cache.schema import init_database
from aletheia_probe.data_models import JournalEntryData
from aletheia_probe.enums import AssessmentType
from aletheia_probe.models import (
    AssessmentResult,
    BackendResult,
    BackendStatus,
    QueryInput,
)


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing with all cache components."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cache_path = Path(f.name)

    # Initialize database schema
    init_database(cache_path)

    # Create cache component instances
    class CacheComponents:
        def __init__(self, db_path):
            self.db_path = db_path
            self.journal_cache = JournalCache(db_path)
            self.acronym_cache = AcronymCache(db_path)
            self.retraction_cache = RetractionCache(db_path)
            self.assessment_cache = AssessmentCache(db_path)
            self.key_value_cache = KeyValueCache(db_path)
            self.data_source_manager = DataSourceManager(db_path)

    cache = CacheComponents(cache_path)
    yield cache

    # Cleanup
    cache_path.unlink(missing_ok=True)


class TestCacheIntegrationJournalDataSource:
    """Integration tests for JournalCache + DataSourceManager interaction.

    These tests verify that JournalCache and DataSourceManager work together correctly
    when managing journal data with associated data sources.
    """

    def test_clear_source_data(self, temp_cache):
        """Test clearing data for a specific source."""
        # Register data sources
        temp_cache.data_source_manager.register_data_source(
            "source_to_clear", "Source to Clear", "predatory"
        )
        temp_cache.data_source_manager.register_data_source(
            "source_to_keep", "Source to Keep", "legitimate"
        )

        # Add test data from multiple sources
        entry1 = JournalEntryData(
            source_name="source_to_clear",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.journal_cache.add_journal_entry(entry1)
        entry2 = JournalEntryData(
            source_name="source_to_keep",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Journal B",
            normalized_name="journal b",
        )
        temp_cache.journal_cache.add_journal_entry(entry2)

        # Clear one source
        cleared_count = temp_cache.data_source_manager.remove_source_data(
            "source_to_clear"
        )

        assert cleared_count == 1

        # Verify correct data was cleared
        remaining_results = temp_cache.journal_cache.search_journals(
            source_name="source_to_keep"
        )
        assert len(remaining_results) == 1
        assert remaining_results[0]["journal_name"] == "Journal B"

    def test_has_source_data(self, temp_cache):
        """Test checking if source has data."""
        # Initially no data
        assert not temp_cache.data_source_manager.has_source_data("test_source")

        # Register data source
        temp_cache.data_source_manager.register_data_source(
            "test_source", "Test Source", "predatory"
        )

        # Add data
        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test journal",
        )
        temp_cache.journal_cache.add_journal_entry(entry)

        # Should now have data
        assert temp_cache.data_source_manager.has_source_data("test_source")

    def test_get_source_statistics(self, temp_cache):
        """Test getting source statistics."""
        # Register data source
        temp_cache.data_source_manager.register_data_source(
            "test_source", "Test Source", "mixed"
        )

        # Add test data
        entry1 = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.journal_cache.add_journal_entry(entry1)
        entry2 = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal B",
            normalized_name="journal b",
        )
        temp_cache.journal_cache.add_journal_entry(entry2)
        entry3 = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Journal C",
            normalized_name="journal c",
        )
        temp_cache.journal_cache.add_journal_entry(entry3)

        stats = temp_cache.data_source_manager.get_source_statistics()

        assert "test_source" in stats
        source_stats = stats["test_source"]
        assert source_stats["total"] == 3
        # print("SS", source_stats)
        # assert source_stats["lists"]["predatory"]["count"] == 2
        # assert source_stats["lists"]["legitimate"]["count"] == 1

    def test_remove_source_data(self, temp_cache):
        """Test removing all data for a source."""
        # Register data source
        temp_cache.data_source_manager.register_data_source(
            "source_to_remove", "Source to Remove", "mixed"
        )

        # Add test data
        entry1 = JournalEntryData(
            source_name="source_to_remove",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal A",
            normalized_name="journal a",
        )
        temp_cache.journal_cache.add_journal_entry(entry1)
        entry2 = JournalEntryData(
            source_name="source_to_remove",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Journal B",
            normalized_name="journal b",
        )
        temp_cache.journal_cache.add_journal_entry(entry2)

        # Remove source data
        removed_count = temp_cache.data_source_manager.remove_source_data(
            "source_to_remove"
        )

        assert removed_count == 2

        # Verify data is gone
        results = temp_cache.journal_cache.search_journals(
            source_name="source_to_remove"
        )
        assert len(results) == 0

    #

    def test_add_journal_entry_with_journal_entry_data(self, temp_cache):
        """Test adding journal entry using JournalEntryData object."""
        # Register the data source first
        temp_cache.data_source_manager.register_data_source(
            name="test_source", display_name="Test Source", source_type="predatory"
        )

        entry_data = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Predatory Journal",
            normalized_name="test_predatory_journal",
            confidence=0.9,
            issn="1234-5678",
            eissn="1234-5679",
            publisher="Sketchy Publisher",
            urls=["http://fake-journal.com"],
            metadata={"impact_factor": "unknown"},
            aliases=["TPJ", "Test Predatory"],
        )

        # This should exercise JournalEntryData handling
        temp_cache.journal_cache.add_journal_entry(entry_data)

        # Verify the entry was added correctly
        journals = temp_cache.journal_cache.search_journals(
            normalized_name="test_predatory_journal"
        )
        assert len(journals) == 1
        # Basic verification that a journal was found
        journal = journals[0]
        assert journal is not None

    def test_add_journal_entry_with_assessment_enum(self, temp_cache):
        """Test handling of AssessmentType enum values."""
        # Register the data source first
        temp_cache.data_source_manager.register_data_source(
            name="test_source", display_name="Test Source", source_type="legitimate"
        )

        entry_data = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.LEGITIMATE,  # Enum with .value attribute
            journal_name="Legitimate Journal",
            normalized_name="legitimate_journal",
            confidence=0.95,
        )

        # This exercises enum value handling
        temp_cache.journal_cache.add_journal_entry(entry_data)

        journals = temp_cache.journal_cache.search_journals(
            normalized_name="legitimate_journal"
        )
        assert len(journals) == 1

    def test_search_journals_with_complex_filters(self, temp_cache):
        """Test complex search scenarios to cover more code paths."""
        # Register data sources first
        temp_cache.data_source_manager.register_data_source(
            name="source1", display_name="Source 1", source_type="predatory"
        )
        temp_cache.data_source_manager.register_data_source(
            name="source2", display_name="Source 2", source_type="legitimate"
        )

        # Add some test data first
        entry1 = JournalEntryData(
            source_name="source1",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal 1",
            normalized_name="test_journal_1",
            issn="1234-5678",
        )
        temp_cache.journal_cache.add_journal_entry(entry1)

        entry2 = JournalEntryData(
            source_name="source2",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Test Journal 2",
            normalized_name="test_journal_2",
            issn="0028-0836",
        )
        temp_cache.journal_cache.add_journal_entry(entry2)

        # Test search by ISSN with different patterns
        results = temp_cache.journal_cache.search_journals(issn="1234-5678")
        assert len(results) == 1

        # Test search by source
        results = temp_cache.journal_cache.search_journals(source_name="source1")
        assert len(results) == 1

        # Test search by normalized name
        results = temp_cache.journal_cache.search_journals(
            normalized_name="test_journal_1"
        )
        assert len(results) == 1

        # Test combined filters
        results = temp_cache.journal_cache.search_journals(source_name="source2")
        assert len(results) == 1

    def test_database_operations_edge_cases(self, temp_cache):
        """Test database operations edge cases."""
        # Register data sources first
        temp_cache.data_source_manager.register_data_source(
            name="source1", display_name="Source 1", source_type="predatory"
        )
        temp_cache.data_source_manager.register_data_source(
            name="source2", display_name="Source 2", source_type="legitimate"
        )

        # Test duplicate normalized names handling
        entry1 = JournalEntryData(
            source_name="source1",
            assessment=AssessmentType.PREDATORY,
            journal_name="Journal Name 1",
            normalized_name="same_normalized_name",
        )
        temp_cache.journal_cache.add_journal_entry(entry1)

        entry2 = JournalEntryData(
            source_name="source2",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Journal Name 2",
            normalized_name="same_normalized_name",
        )
        temp_cache.journal_cache.add_journal_entry(entry2)

        # Should handle duplicates gracefully
        results = temp_cache.journal_cache.search_journals(
            normalized_name="same_normalized_name"
        )
        assert len(results) >= 1

    def test_metadata_and_url_handling(self, temp_cache):
        """Test metadata and URL handling to improve coverage."""
        # Register data source first
        temp_cache.data_source_manager.register_data_source(
            name="complex_source",
            display_name="Complex Source",
            source_type="predatory",
        )

        # Test with complex metadata and URLs
        entry = JournalEntryData(
            source_name="complex_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Complex Journal",
            normalized_name="complex_journal",
            urls=["http://example1.com", "http://example2.com"],
            metadata={"key1": "value1", "key2": {"nested": "value"}},
            aliases=["CJ", "Complex J", "The Complex Journal"],
        )
        temp_cache.journal_cache.add_journal_entry(entry)

        results = temp_cache.journal_cache.search_journals(
            normalized_name="complex_journal"
        )
        assert len(results) == 1

    def test_get_source_statistics_comprehensive(self, temp_cache):
        """Test comprehensive source statistics functionality."""
        # Register data sources first
        for i in range(5):
            temp_cache.data_source_manager.register_data_source(
                name=f"source_{i}", display_name=f"Source {i}", source_type="predatory"
            )

        # Add data from multiple sources
        for i in range(5):
            entry = JournalEntryData(
                source_name=f"source_{i}",
                assessment=AssessmentType.PREDATORY,
                journal_name=f"Journal {i}",
                normalized_name=f"journal_{i}",
            )
            temp_cache.journal_cache.add_journal_entry(entry)

        stats = temp_cache.data_source_manager.get_source_statistics()
        assert len(stats) >= 5

        # Test that source_0 appears in the statistics
        assert "source_0" in stats

    def test_add_journal_entry_metadata_integer_type(self, temp_cache):
        """Test adding journal entry with integer metadata."""
        temp_cache.data_source_manager.register_data_source(
            name="test_source",
            display_name="Test Source",
            source_type="unknown",
        )

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test_journal",
            metadata={"count": 42},
        )

        temp_cache.journal_cache.add_journal_entry(entry)

        # Verify metadata was stored
        results = temp_cache.journal_cache.search_journals(
            normalized_name="test_journal"
        )
        assert len(results) > 0

    def test_add_journal_entry_metadata_boolean_type(self, temp_cache):
        """Test adding journal entry with boolean metadata."""
        temp_cache.data_source_manager.register_data_source(
            name="test_source",
            display_name="Test Source",
            source_type="unknown",
        )

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test_journal",
            metadata={"is_active": True},
        )

        temp_cache.journal_cache.add_journal_entry(entry)

        results = temp_cache.journal_cache.search_journals(
            normalized_name="test_journal"
        )
        assert len(results) > 0

    def test_search_journals_with_journal_name_filter(self, temp_cache):
        """Test searching journals with journal_name filter."""
        temp_cache.data_source_manager.register_data_source(
            name="test_source",
            display_name="Test Source",
            source_type="unknown",
        )

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="International Journal of Testing",
            normalized_name="international_journal_testing",
        )

        temp_cache.journal_cache.add_journal_entry(entry)

        # Search with journal_name parameter
        results = temp_cache.journal_cache.search_journals(journal_name="Testing")

        assert len(results) > 0
        assert any("Testing" in r.get("display_name", "") for r in results)

    def test_search_journals_metadata_integer_conversion(self, temp_cache):
        """Test that integer metadata is converted correctly."""
        temp_cache.data_source_manager.register_data_source(
            name="test_source",
            display_name="Test Source",
            source_type="unknown",
        )

        entry = JournalEntryData(
            source_name="test_source",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test_journal",
            metadata={"year": 2023},
        )

        temp_cache.journal_cache.add_journal_entry(entry)

        results = temp_cache.journal_cache.search_journals(
            normalized_name="test_journal"
        )
        assert len(results) > 0
        if results[0].get("metadata"):
            metadata = json.loads(results[0]["metadata"])
            assert metadata.get("year") == 2023

    def test_find_conflicts(self, temp_cache):
        """Test finding journals with conflicting assessments."""
        temp_cache.data_source_manager.register_data_source(
            name="source1",
            display_name="Source 1",
            source_type="unknown",
        )

        temp_cache.data_source_manager.register_data_source(
            name="source2",
            display_name="Source 2",
            source_type="unknown",
        )

        # Add same journal to both sources with different assessments
        entry1 = JournalEntryData(
            source_name="source1",
            assessment=AssessmentType.PREDATORY,
            journal_name="Test Journal",
            normalized_name="test_journal",
        )

        entry2 = JournalEntryData(
            source_name="source2",
            assessment=AssessmentType.LEGITIMATE,
            journal_name="Test Journal",
            normalized_name="test_journal",
        )

        temp_cache.journal_cache.add_journal_entry(entry1)
        temp_cache.journal_cache.add_journal_entry(entry2)

        conflicts = temp_cache.data_source_manager.find_conflicts()

        assert len(conflicts) > 0
        assert any(c["normalized_name"] == "test_journal" for c in conflicts)

    def test_cache_special_characters_handling(self, temp_cache):
        """Test cache handles special characters in journal names.

        Validates that journals with special characters, unicode,
        and various encodings are properly stored and retrieved.
        """
        # Register test source first
        temp_cache.data_source_manager.register_data_source(
            name="test",
            display_name="Test Source",
            source_type="unknown",
        )

        # Test journals with special characters
        special_journals = [
            "Journal of Test™ & Research®",
            "学术期刊 (Academic Journal)",
            "Журнал Науки",  # Russian
            "مجلة العلوم",  # Arabic
            "Journal with 'quotes' and \"double quotes\"",
            "Journal with semicolons; and colons:",
        ]

        for i, journal in enumerate(special_journals):
            entry = JournalEntryData(
                source_name="test",
                assessment=AssessmentType.LEGITIMATE,
                journal_name=journal,
                normalized_name=f"special {i}",
            )
            temp_cache.journal_cache.add_journal_entry(entry)

        # Verify all can be retrieved
        for i, journal in enumerate(special_journals):
            results = temp_cache.journal_cache.search_journals(
                normalized_name=f"special {i}"
            )
            assert len(results) > 0, (
                f"Should find journal with special chars: {journal}"
            )
            assert results[0]["display_name"] == journal

    def test_cache_large_dataset(self, temp_cache):
        """Test cache performance with larger dataset.

        Validates that cache operations remain functional with
        a reasonable number of entries.
        """
        # Register test sources first
        for j in range(10):
            temp_cache.data_source_manager.register_data_source(
                name=f"source_{j}",
                display_name=f"Source {j}",
                source_type="unknown",
            )

        # Add 1000 journals
        num_journals = 1000
        for i in range(num_journals):
            entry = JournalEntryData(
                source_name=f"source_{i % 10}",  # 10 different sources
                assessment=(
                    AssessmentType.LEGITIMATE
                    if i % 3 == 0
                    else AssessmentType.PREDATORY
                ),
                journal_name=f"Journal {i:04d}",
                normalized_name=f"journal {i:04d}",
            )
            temp_cache.journal_cache.add_journal_entry(entry)

        # Test searching still works
        results = temp_cache.journal_cache.search_journals(
            normalized_name="journal 0500"
        )
        assert len(results) > 0, "Should find journal in large dataset"

        # Test source filtering works
        source_results = temp_cache.journal_cache.search_journals(
            source_name="source_5"
        )
        assert len(source_results) == 100, (
            "Should find exactly 100 journals from source_5"
        )
