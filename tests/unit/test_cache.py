# SPDX-License-Identifier: MIT
"""Tests for the cache management module."""

import logging
import sqlite3
import tempfile
import threading
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


class TestAcronymMapping:
    """Test cases for conference acronym mapping functionality."""

    def test_store_acronym_mapping_new_entry(self, temp_cache):
        """Test storing a new acronym mapping."""
        temp_cache.store_acronym_mapping(
            acronym="ICML", full_name="International Conference on Machine Learning"
        )

        # Verify the mapping was stored (returns normalized lowercase form)
        result = temp_cache.get_full_name_for_acronym("ICML")
        assert result == "international conference on machine learning"

    def test_store_acronym_mapping_case_insensitive(self, temp_cache):
        """Test that acronym lookup is case-insensitive."""
        temp_cache.store_acronym_mapping(
            acronym="CVPR", full_name="Conference on Computer Vision"
        )

        # Should work with different cases (returns normalized lowercase form)
        assert (
            temp_cache.get_full_name_for_acronym("CVPR")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("cvpr")
            == "conference on computer vision"
        )
        assert (
            temp_cache.get_full_name_for_acronym("CvPr")
            == "conference on computer vision"
        )

    def test_store_acronym_mapping_no_warn_on_year_variation(self, temp_cache, caplog):
        """Test that no warning is logged for year variations of same conference."""
        caplog.set_level(logging.WARNING)

        # Store initial mapping with year
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        )

        # Store same conference without year - should not warn
        temp_cache.store_acronym_mapping(
            acronym="CVPR",
            full_name="IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        )

        # Verify no warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 0

    def test_store_acronym_mapping_no_warn_on_ordinal_variation(
        self, temp_cache, caplog
    ):
        """Test that no warning is logged for ordinal variations."""
        caplog.set_level(logging.WARNING)

        # Store with ordinal
        temp_cache.store_acronym_mapping(
            acronym="ICML",
            full_name="37th International Conference on Machine Learning",
        )

        # Store without ordinal - should not warn
        temp_cache.store_acronym_mapping(
            acronym="ICML", full_name="International Conference on Machine Learning"
        )

        # Verify no warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 0

    def test_store_acronym_mapping_warns_on_different_conferences(
        self, temp_cache, caplog
    ):
        """Test that warning is logged when acronym maps to truly different conferences."""
        caplog.set_level(logging.WARNING)

        # Store first conference
        temp_cache.store_acronym_mapping(
            acronym="AI", full_name="Artificial Intelligence Conference"
        )

        # Store different conference with same acronym - should warn
        temp_cache.store_acronym_mapping(
            acronym="AI", full_name="Algorithms and Informatics Symposium"
        )

        # Verify warning was logged
        warnings = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(warnings) == 1
        assert "already maps to" in warnings[0].message
        assert "artificial intelligence conference" in warnings[0].message

    def test_store_acronym_mapping_source_tracking(self, temp_cache):
        """Test that the source of acronym mappings is tracked."""
        temp_cache.store_acronym_mapping(
            acronym="NeurIPS",
            full_name="Neural Information Processing Systems",
            source="bibtex_extraction",
        )

        # Verify the mapping exists (source is tracked internally, returns normalized form)
        result = temp_cache.get_full_name_for_acronym("NeurIPS")
        assert result == "neural information processing systems"

    def test_are_conference_names_equivalent_identical(self, temp_cache):
        """Test equivalence check for identical names."""
        assert temp_cache._are_conference_names_equivalent(
            "Machine Learning Conference", "Machine Learning Conference"
        )

    def test_are_conference_names_equivalent_case_insensitive(self, temp_cache):
        """Test equivalence check is case-insensitive."""
        assert temp_cache._are_conference_names_equivalent(
            "Machine Learning Conference", "machine learning conference"
        )

    def test_are_conference_names_equivalent_year_prefix(self, temp_cache):
        """Test equivalence with year prefix."""
        assert temp_cache._are_conference_names_equivalent(
            "2022 IEEE/CVF Conference on Computer Vision",
            "IEEE/CVF Conference on Computer Vision",
        )

    def test_are_conference_names_equivalent_year_suffix(self, temp_cache):
        """Test equivalence with year suffix."""
        assert temp_cache._are_conference_names_equivalent(
            "Conference on Machine Learning 2023",
            "Conference on Machine Learning",
        )

    def test_are_conference_names_equivalent_edition_markers(self, temp_cache):
        """Test equivalence with edition markers."""
        assert temp_cache._are_conference_names_equivalent(
            "2022 edition International Conference",
            "International Conference",
        )
        assert temp_cache._are_conference_names_equivalent(
            "International Conference edition 2022",
            "International Conference",
        )

    def test_are_conference_names_equivalent_ordinals(self, temp_cache):
        """Test equivalence with ordinal numbers."""
        assert temp_cache._are_conference_names_equivalent(
            "37th International Conference on Machine Learning",
            "International Conference on Machine Learning",
        )
        assert temp_cache._are_conference_names_equivalent(
            "1st Workshop on Neural Networks",
            "Workshop on Neural Networks",
        )
        assert temp_cache._are_conference_names_equivalent(
            "22nd Annual Conference",
            "Annual Conference",
        )

    def test_are_conference_names_equivalent_different_conferences(self, temp_cache):
        """Test that truly different conferences are not equivalent."""
        assert not temp_cache._are_conference_names_equivalent(
            "Artificial Intelligence Conference",
            "Algorithms and Informatics Symposium",
        )
        assert not temp_cache._are_conference_names_equivalent("AAAI", "AI Conference")

    def test_are_conference_names_equivalent_substring_with_length_check(
        self, temp_cache
    ):
        """Test that short substrings don't match to avoid false positives."""
        # Short names (< 10 chars) should not match via substring
        assert not temp_cache._are_conference_names_equivalent("AI", "AAAI")
        assert not temp_cache._are_conference_names_equivalent("ML", "ICML")

        # But longer names can match via substring after year/ordinal removal
        assert temp_cache._are_conference_names_equivalent(
            "International Conference on Machine Learning and Applications",
            "International Conference on Machine Learning",
        )

    def test_are_conference_names_equivalent_complex_variations(self, temp_cache):
        """Test complex real-world variations."""
        # Real example from issue #90
        assert temp_cache._are_conference_names_equivalent(
            "2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
            "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        )

        # Multiple years in name
        assert temp_cache._are_conference_names_equivalent(
            "2023 25th International Conference",
            "International Conference",
        )

    def test_store_acronym_mapping_overwrites_with_latest(self, temp_cache):
        """Test that newer mappings overwrite older ones."""
        # Store initial mapping
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2022"
        )

        # Store updated mapping (equivalent, just different year)
        temp_cache.store_acronym_mapping(
            acronym="TEST", full_name="Test Conference 2023"
        )

        # Both normalize to the same generic form (years stripped)
        result = temp_cache.get_full_name_for_acronym("TEST")
        assert result == "test conference"
